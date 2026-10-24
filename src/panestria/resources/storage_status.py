"""Demand-driven, coalesced owner metadata sampling; no timer/model or cleanup."""

import json
import math
import threading
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from panestria.config_storage import load_storage_settings
from panestria.contracts.storage_status import StorageStatus
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.resources.storage import StorageReport, StorageSettings, inspect_storage
from panestria.resources.storage_history import StorageHistory


class StorageObserver:
    """At most one daemon probe. A stuck OS read never queues more probe threads."""

    def __init__(
        self,
        actor: Actor,
        path: Path,
        *,
        probe: Callable[..., StorageReport] = inspect_storage,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.actor, self.path, self.probe, self.clock = actor, path, probe, clock
        self.lock = threading.Lock()
        self.closed, self.inflight = False, False
        self.started, self.next_check, self.last_probe = 0.0, 0.0, -math.inf
        self.previous: StorageReport | None = None
        self.previous_settings: StorageSettings | None = None
        self.value = self._empty("COLLECTING", "collecting")

    def _empty(self, state: str, reason: str, enabled: bool | None = None) -> StorageStatus:
        return StorageStatus.model_validate_json(
            json.dumps(
                {
                    "owner_id": self.actor.owner_id,
                    "project_id": self.actor.project_id,
                    "state": state,
                    "reason": reason,
                    "notifications_enabled": enabled,
                }
            )
        )

    def view(self, actor: Actor) -> StorageStatus:
        if (actor.owner_id, actor.project_id) != (self.actor.owner_id, self.actor.project_id):
            raise KernelDenied("not_found")
        with self.lock:
            if self.closed:
                return self._empty("UNAVAILABLE", "closed")
            now = self.clock()
            if self.inflight:
                if now - self.started >= 35:
                    return self._empty("STALLED", "probe_deadline_exceeded", self.value.notifications_enabled)
                return self.value.model_copy(
                    update={"state": "COLLECTING", "reason": "collecting", "next_check_seconds": 1}
                )
            if now >= self.next_check:
                self.inflight, self.started = True, now
                # No file I/O on the HTTP/event loop. Only this owned daemon can
                # load private settings or invoke the existing bounded probes.
                threading.Thread(target=self._collect, daemon=True).start()
                return self.value.model_copy(
                    update={"state": "COLLECTING", "reason": "collecting", "next_check_seconds": 1}
                )
            return self.value.model_copy(update={"next_check_seconds": max(1, math.ceil(self.next_check - now))})

    def _collect(self) -> None:
        previous, settings = None, None
        result = self._empty("UNAVAILABLE", "probe_unavailable")
        try:
            with self.lock:
                if self.closed:
                    return
            settings = load_storage_settings(self.path)
            if not settings.notifications_enabled:
                result = self._empty("DISABLED", "disabled", False)
            else:
                with self.lock:
                    if self.closed:
                        return
                    previous = self.previous if settings == self.previous_settings else None
                    due = self.last_probe + settings.interval_seconds if previous is not None else self.last_probe + 60
                if self.clock() < due:
                    # Check opt-out/settings at most once a minute while keeping
                    # the configured full-probe interval and original sample.
                    result = (
                        self.value
                        if previous is not None
                        else self._empty("UNAVAILABLE", "configuration_changed", True)
                    )
                else:
                    with self.lock:
                        if self.closed:
                            return
                        self.last_probe = self.clock()
                    accepted = False
                    with StorageHistory(settings) as history:
                        retained_previous = history.previous()
                        previous = previous or retained_previous
                        report = self.probe(settings, previous=previous)
                        current = load_storage_settings(self.path)
                        with self.lock:
                            closed = self.closed
                        if current != settings or closed:
                            result = (
                                self._empty("DISABLED", "disabled", False)
                                if not current.notifications_enabled
                                else self._empty("UNAVAILABLE", "configuration_changed", True)
                            )
                        elif self.clock() - self.started >= 35:
                            result = self._empty("UNAVAILABLE", "probe_deadline_exceeded", True)
                        else:
                            report = history.retain(report)
                            accepted = True
                    if accepted:
                        current = load_storage_settings(self.path)
                        if current != settings:
                            accepted = False
                            result = (
                                self._empty("DISABLED", "disabled", False)
                                if not current.notifications_enabled
                                else self._empty("UNAVAILABLE", "configuration_changed", True)
                            )
                        elif self.clock() - self.started >= 35:
                            accepted = False
                            result = self._empty("UNAVAILABLE", "probe_deadline_exceeded", True)
                    if accepted:
                        capacity = asdict(report.capacity)
                        capacity.pop("device")  # No private path/device identity in the view.
                        result = StorageStatus.model_validate_json(
                            json.dumps(
                                {
                                    "owner_id": self.actor.owner_id,
                                    "project_id": self.actor.project_id,
                                    "state": "OBSERVED",
                                    "reason": "ready",
                                    "notifications_enabled": True,
                                    "sample_interval_seconds": settings.interval_seconds,
                                    "observed_at": report.observed_at,
                                    "capacity": capacity,
                                    "components": [asdict(v) for v in report.components],
                                    "warnings": [asdict(v) for v in report.warnings],
                                    "timeshift_status": report.timeshift["status"],
                                    "timeshift_schedules": report.timeshift.get("schedules"),
                                }
                            )
                        )
                        with self.lock:
                            if not self.closed:
                                self.previous, self.previous_settings = report, settings
        except Exception:
            # Neither a private locator nor arbitrary probe exception is exposed.
            result = self._empty("UNAVAILABLE", "probe_unavailable")
        finally:
            with self.lock:
                if not self.closed:
                    self.value = result
                    self.next_check = self.clock() + 60
                    if result.state == "DISABLED":
                        self.previous, self.previous_settings = None, None
                self.inflight = False

    def close(self) -> None:
        with self.lock:
            self.closed = True
            self.previous, self.previous_settings = None, None
            self.value = self._empty("UNAVAILABLE", "closed")
        # No join/wait on a potentially stuck filesystem read; no new collector
        # is started and an already running daemon can never publish after close.
