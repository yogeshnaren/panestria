"""One explicit finite foreground handoff; no startup scan or background queue."""

import json
import re
import threading
from pathlib import Path
from typing import Any

import psycopg

from panestria.config_build import load_build_settings
from panestria.contracts.build import canonical_sha256
from panestria.contracts.plan_run import PlanRunReturn, PlanRunStorage, PlanRunView
from panestria.execution.native_plan import NativePlanRunner
from panestria.execution.owner_build import OwnerBuild
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.plan_lifecycle import PlanLifecycle
from panestria.kernel.plan_run import PlanRunStore
from panestria.kernel.uow import UnitOfWork


class MissionRunService:
    def __init__(self, path: Path, actor: Actor, dsn: str):
        self.path, self.actor, self.dsn = path, actor, dsn
        self.settings = load_build_settings(path)
        if (str(self.settings.owner_id), str(self.settings.project_id)) != (actor.owner_id, actor.project_id):
            raise KernelDenied("mission_run_scope_mismatch")
        self.configuration = canonical_sha256(self.settings.model_dump(mode="json"))
        self.store = PlanRunStore()
        self.lock = threading.Lock()
        self.active: tuple[str, threading.Thread, threading.Event] | None = None
        self.closed = False

    def connect(self) -> psycopg.Connection[Any]:
        return psycopg.connect(self.dsn, connect_timeout=2, options="-c statement_timeout=2000 -c lock_timeout=1000")

    def observe(self, view: PlanRunView) -> PlanRunView:
        with self.lock:
            running = self.active is not None and self.active[0] == view.plan_id and self.active[1].is_alive()
        return view.model_copy(update={"controller_active": bool(running)})

    def wake(self, plan_id: str, request_id: str) -> None:
        # Called only after the HTTP transaction COMMIT was acknowledged. This
        # memory flag is an optimization; canonical claims enforce cross-process
        # at-most-once dispatch, including after a lost commit acknowledgement.
        with self.lock:
            if self.closed or (self.active is not None and self.active[1].is_alive()):
                return
            stop = threading.Event()
            worker = threading.Thread(
                target=self._drive, args=(plan_id, request_id, stop), daemon=True, name="panestria-mission-build"
            )
            self.active = plan_id, worker, stop
            worker.start()

    def _drive(self, plan_id: str, request_id: str, stop: threading.Event) -> None:
        try:
            with self.connect() as c:
                record = self.store.claim(UnitOfWork(c), self.actor, plan_id, request_id, self.configuration)
            # No code capable of worker dispatch is reached until claim COMMIT
            # has returned successfully. An uncertain claim is never adopted.
        except Exception:
            return
        outcome, status = "CONTROLLER_ERROR", "UNCONFIRMED"
        try:
            settings = load_build_settings(self.path)
            if canonical_sha256(settings.model_dump(mode="json")) != self.configuration:
                raise KernelDenied("mission_run_configuration_changed")
            if stop.is_set():
                status, outcome = "STOPPED", "RETURNED"
            else:

                def storage_observed(value: dict[str, Any]) -> None:
                    report = value.get("report", {})
                    notice = PlanRunStorage.model_validate_json(
                        json.dumps(
                            {
                                "record_sha256": record.sha256(),
                                "decision": value["decision"],
                                "reason": value["reason"],
                                "warnings": [w["code"] for w in report.get("warnings", [])],
                                "available_bytes": report.get("capacity", {}).get("available_bytes"),
                                "anticipated_write_bytes": value.get("anticipated_write_bytes"),
                            }
                        )
                    )
                    with self.connect() as c:
                        self.store.storage(UnitOfWork(c), self.actor, record, notice)

                runner = NativePlanRunner(OwnerBuild(settings, self.dsn), on_storage_observation=storage_observed)
                runner.cancel = stop
                value = runner.run(plan_id, public_subscription_run=True)
                candidate = value.get("status")
                status = (
                    candidate if isinstance(candidate, str) and re.fullmatch(r"[A-Z_]{1,64}", candidate) else status
                )
                outcome = "RETURNED"
        except KernelDenied:
            outcome, status = "ADMISSION_DENIED", "WAIT"
        except Exception:
            pass  # Never retain/echo arbitrary native output, paths or credential errors.
        try:
            result = PlanRunReturn.model_validate(
                {
                    "request_id": request_id,
                    "record_sha256": record.sha256(),
                    "outcome": outcome,
                    "runner_status": status,
                }
            )
            with self.connect() as c:
                self.store.finish(UnitOfWork(c), self.actor, plan_id, result, self.configuration)
        except Exception:
            # A missing return stays CLAIMED_UNCONFIRMED. It grants no redispatch
            # or claim release even when this Python thread has physically ended.
            pass

    def signal_cancel(self, plan_id: str) -> None:
        with self.lock:
            if self.active is not None and self.active[0] == plan_id:
                self.active[2].set()

    def close(self) -> None:
        with self.lock:
            self.closed = True
            current = self.active
            if current is None or not current[1].is_alive():
                return
            current[2].set()
        # Server shutdown withdraws this server's active finite intent. Browser
        # reload/logout is not server shutdown and never resubmits/cancels a job.
        try:
            with self.connect() as c:
                view = self.store.inspect(UnitOfWork(c), self.actor, current[0], self.configuration)
                PlanLifecycle().cancel(UnitOfWork(c), self.actor, current[0], view.plan_sha256)
        except Exception:
            pass  # Canonical uncertain tasks/claims survive; no cleanup/deletion.
