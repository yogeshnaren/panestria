"""Coarse foreground headroom and one resident inference slot; never a cloud fallback."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass
from uuid import uuid4

from panestria.contracts.hardware import HardwareManifest
from panestria.contracts.inference import InferenceUnavailable


@dataclass(frozen=True)
class Admission:
    decision: str
    reasons: tuple[str, ...]
    cpu_limit: int = 2
    ram_limit_bytes: int = 2560 * 1024 * 1024
    gpu_partition_guaranteed: bool = False
    gpu_model_budget_gib: float = 2.5
    gpu_foreground_reserve_gib: float = 1.0


def admit(manifest: HardwareManifest, *, gpu: bool, foreground_active: bool = True) -> Admission:
    # Resident host cgroup ceiling plus foreground reserve. Free capacity is unknown
    # when absent; total RAM cannot substitute for currently available capacity.
    headroom = 2.0 if foreground_active else 1.0
    if manifest.ram_available_gib is None or manifest.disk_free_gib is None:
        return Admission("UNAVAILABLE", ("capacity_unknown",))
    if manifest.ram_available_gib < 2.5 + headroom:
        return Admission("WAIT", ("foreground_ram_pressure",))
    if manifest.disk_free_gib < 2.0:
        return Admission("WAIT", ("disk_pressure",))
    if manifest.on_ac_power is not True:
        return Admission("UNAVAILABLE", ("battery_or_power_unknown",))
    if manifest.thermal_state == "HOT":
        return Admission("WAIT", ("thermal_pressure",))
    if manifest.logical_cores is None or manifest.logical_cores < 4:
        return Admission("UNAVAILABLE", ("cpu_headroom_unknown_or_insufficient",))
    # Reserve the complete model profile plus foreground VRAM even if the primary
    # is already resident. This is an admission estimate, not an OS VRAM partition.
    if gpu and not any(g.free_gib is not None and g.free_gib >= 2.5 + 1.0 for g in manifest.accelerators):
        return Admission("WAIT", ("gpu_pressure_or_unknown",))
    return Admission("PERMIT", ("coarse_caps_and_foreground_reserve",))


class RuntimeGovernor:
    """One event loop, bounded FIFO admission. Cancellation removes queued tickets."""

    def __init__(self, *, max_queue: int = 2) -> None:
        if not 0 <= max_queue <= 8:
            raise ValueError("queue_limit")
        self.max_queue = max_queue
        self.active: str | None = None
        self.queue: deque[str] = deque()
        self.stopped = False

    async def acquire(self, *, wait_seconds: float = 5.0) -> str:
        if self.stopped:
            raise InferenceUnavailable("admissions_stopped")
        if not 0 < wait_seconds <= 60:
            raise ValueError("queue_deadline")
        if (self.active is not None or self.queue) and len(self.queue) >= self.max_queue:
            raise InferenceUnavailable("queue_capacity")
        ticket, deadline = uuid4().hex, time.monotonic() + wait_seconds
        self.queue.append(ticket)
        try:
            while True:
                if self.stopped:
                    raise InferenceUnavailable("admissions_stopped")
                if self.active is None and self.queue[0] == ticket:
                    self.queue.popleft()
                    self.active = ticket
                    return ticket
                if time.monotonic() >= deadline:
                    raise InferenceUnavailable("queued_deadline_exceeded")
                await asyncio.sleep(0.02)
        except BaseException:
            self.queue.remove(ticket)
            raise

    def release(self, ticket: str) -> None:
        if self.active != ticket:
            raise ValueError("admission_identity_mismatch")
        self.active = None

    def stop_admissions(self) -> None:
        self.stopped = True  # Existing work retains its ticket; no new work is admitted.

    def status(self) -> dict[str, object]:
        return {"active": self.active is not None, "queued": len(self.queue), "admissions_stopped": self.stopped}
