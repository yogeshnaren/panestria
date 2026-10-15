"""Deterministic headroom and real asyncio queue cancellation, without stressing the desktop."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from panestria.contracts.inference import InferenceUnavailable
from panestria.resources.admission import RuntimeGovernor, admit
from panestria.resources.hardware import HardwareProbe

ARCHIVE = Path(__file__).resolve().parents[2] / "docs/specification/attachments/agentos-skills-v0.1.0.zip"


def test_headroom_never_selects_cloud() -> None:
    manifest = HardwareProbe(ARCHIVE).collect(preset="omen-8gb")
    assert admit(manifest, gpu=True).decision == "PERMIT"
    for changes, reason in [
        ({"ram_available_gib": 4.0}, "foreground_ram_pressure"),
        ({"disk_free_gib": 0.5}, "disk_pressure"),
        ({"accelerators": ()}, "gpu_pressure_or_unknown"),
        ({"thermal_state": "HOT"}, "thermal_pressure"),
        ({"ram_available_gib": None}, "capacity_unknown"),
        ({"on_ac_power": False}, "battery_or_power_unknown"),
    ]:
        decision = admit(manifest.model_copy(update=changes), gpu=True)
        assert reason in decision.reasons and decision.decision in {"WAIT", "UNAVAILABLE"}
        assert not decision.gpu_partition_guaranteed
    assert admit(manifest.model_copy(update={"accelerators": ()}), gpu=False).decision == "PERMIT"


def test_bounded_fifo_cancel_and_stop(record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-018-TC03")
    record_property("source_clauses", "AOS-018-F02,AOS-018-F03,AOS-018-AC02,AOS-018-AC03")

    async def scenario() -> None:
        governor = RuntimeGovernor(max_queue=1)
        first = await governor.acquire()
        waiter = asyncio.create_task(governor.acquire(wait_seconds=0.2))
        await asyncio.sleep(0.03)
        assert governor.status()["queued"] == 1
        with pytest.raises(InferenceUnavailable, match="queue_capacity"):
            await governor.acquire()
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert governor.status()["queued"] == 0 and governor.active == first
        with pytest.raises(InferenceUnavailable, match="queued_deadline_exceeded"):
            await governor.acquire(wait_seconds=0.05)
        governor.release(first)
        second = await governor.acquire()
        queued = asyncio.create_task(governor.acquire())
        await asyncio.sleep(0.03)
        governor.stop_admissions()
        with pytest.raises(InferenceUnavailable, match="admissions_stopped"):
            await queued
        with pytest.raises(InferenceUnavailable, match="admissions_stopped"):
            await governor.acquire()
        assert governor.active == second
        governor.release(second)
        assert governor.status() == {"active": False, "queued": 0, "admissions_stopped": True}

    asyncio.run(scenario())
