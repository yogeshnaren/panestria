"""One explicit finite preferred-provider job, no daemon, fallback or auto-merge."""

from typing import Any
from uuid import uuid4

from panestria.contracts.background_run import BackgroundRun
from panestria.contracts.build import canonical_sha256
from panestria.contracts.hardware import HardwareManifest
from panestria.contracts.native_tools import ToolScope
from panestria.contracts.plan import StoredPlan
from panestria.execution.background_account import account_reports, collect_account
from panestria.execution.native_plan import NativePlanRunner
from panestria.execution.owner_build import OwnerBuild
from panestria.execution.proposal_demo import _lock
from panestria.execution.worker_authority import WorkerAuthority
from panestria.kernel.background_run import BACKGROUND_SESSION_LOCK, BackgroundRunService
from panestria.kernel.build import BuildEvidenceService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.scheduler import Queued, Scheduled
from panestria.kernel.uow import UnitOfWork


class BackgroundPlanRunner(NativePlanRunner):
    maximum_parallel = 1

    def __init__(self, owner: OwnerBuild, item_id: str, **kwargs: Any) -> None:
        super().__init__(owner, **kwargs)
        self.item_id = item_id
        self.service = BackgroundRunService(account_reports(owner), self.evidence)
        self.run_record: BackgroundRun | None = None
        self.wait_reason: str | None = None

    def _operation_lock(self) -> Any:
        # Do not hold the foreground operation lock for a background job.
        return _lock(self.owner.settings.root / "background-operation.lock")

    def _preflight(self, plan_id: str) -> StoredPlan:
        # Existing current-policy, source/runtime certificate, exact inventory,
        # Git base and pinned adapter checks remain mandatory before admission.
        plan = super()._preflight(plan_id)
        with self.owner.connect() as c:
            binding = self.service.accounts.binding(UnitOfWork(c), self.owner.actor, self.item_id)
            if binding.request.plan_id != plan_id:
                raise KernelDenied("background_plan_binding_changed")
            self.service._eligibility(UnitOfWork(c), self.owner.actor, binding)
        digest = collect_account(self.owner, binding.request.policy.quota_windows[0].account_ref)
        with self.owner.connect() as c:
            self.run_record = self.service.start(UnitOfWork(c), self.owner.actor, self.item_id, digest, str(uuid4()))
        return plan

    def _claim(self, plan: StoredPlan, capacity: HardwareManifest) -> Scheduled | Queued:
        assert self.run_record is not None
        with self.owner.connect() as c:
            binding = self.service.accounts.binding(UnitOfWork(c), self.owner.actor, self.item_id)
        try:
            digest = collect_account(self.owner, binding.request.policy.quota_windows[0].account_ref)
            with self.owner.connect() as c:
                result = self.service.claim(UnitOfWork(c), self.owner.actor, self.run_record, digest, capacity)
        except KernelDenied as exc:
            result = Queued(binding.task_id, exc.code)
        if isinstance(result, Queued):
            self.wait_reason = result.reason
        return result

    def _worker_authority(self, job: Scheduled, scope: ToolScope) -> WorkerAuthority:
        run = self.run_record
        if run is None or (str(scope.task_id), str(scope.attempt_id), scope.lease_epoch) != (
            job.lease.task_id,
            job.lease.attempt_id,
            job.lease.epoch,
        ):
            raise KernelDenied("background_worker_binding_required")

        def authorize(connection: Any) -> None:
            self.service.authorize_worker(UnitOfWork(connection), self.owner.actor, run, scope)

        def refresh() -> None:
            # Bounded pinned CLI metadata only, immediately before disclosure
            # and after return. No provider/model prompt or raw identity archive.
            with self.owner.connect() as c:
                authorize(c)
                binding = self.service.accounts.binding(UnitOfWork(c), self.owner.actor, self.item_id)
            digest = collect_account(self.owner, binding.request.policy.quota_windows[0].account_ref)
            with self.owner.connect() as c:
                self.service.authorize_worker(UnitOfWork(c), self.owner.actor, run, scope, observation_sha256=digest)

        return WorkerAuthority(canonical_sha256({"run": run.sha256(), "scope": scope.sha256()}), authorize, refresh)

    def run_item(self, *, allow_background_subscription_run: bool) -> dict[str, Any]:
        if allow_background_subscription_run is not True:
            raise KernelDenied("explicit_background_subscription_run_required")
        owner = self.owner
        # Held session lock plus immutable start/return facts cover independent
        # controllers and crashes without making task heartbeats a second store.
        with owner.connect() as guard:
            locked = guard.execute("SELECT pg_try_advisory_lock(%s,%s)", BACKGROUND_SESSION_LOCK).fetchone()
            guard.commit()
            if locked != (True,):
                return {"status": "WAIT", "reason": "background_controller_already_active", "item_id": self.item_id}
            reason = "controller_exception"
            try:
                with owner.connect() as c:
                    binding = self.service.accounts.binding(UnitOfWork(c), owner.actor, self.item_id)
                try:
                    result: dict[str, Any] = dict(super().run(binding.request.plan_id, public_subscription_run=True))
                except KernelDenied as exc:
                    result = {"status": "WAIT", "reason": exc.code, "item_id": self.item_id}
                if self.wait_reason:
                    result["background_wait_reason"] = self.wait_reason
                if self.run_record is not None:
                    result["background_run_sha256"] = self.run_record.sha256()
                    result["background_billing_evidence"] = self.run_record.billing_evidence
                    result["billing_provider_verified"] = False
                    if any(r.get("reason") == "quota_unavailable" for r in result.get("worker_observations", [])):
                        with owner.connect() as c:
                            self.service.record_limit(UnitOfWork(c), owner.actor, self.run_record)
                reason = "controller_returned"
                return result
            finally:
                if self.run_record is not None:
                    with owner.connect() as c:
                        self.service.finish(UnitOfWork(c), owner.actor, self.run_record, reason)
                # Session lock is released by connection close, including errors.


def reconcile_run(owner: OwnerBuild, item_id: str, run_sha256: str) -> dict[str, Any]:
    with owner.connect() as guard:
        locked = guard.execute("SELECT pg_try_advisory_lock(%s,%s)", BACKGROUND_SESSION_LOCK).fetchone()
        guard.commit()
        if locked != (True,):
            raise KernelDenied("background_controller_still_active")
        with owner.connect() as c:
            return BackgroundRunService(account_reports(owner), BuildEvidenceService(owner.reports)).reconcile(
                UnitOfWork(c), owner.actor, item_id, run_sha256
            )


def select_next(owner: OwnerBuild) -> dict[str, Any]:
    with owner.connect() as c:
        return BackgroundRunService(account_reports(owner), BuildEvidenceService(owner.reports)).next_candidate(
            UnitOfWork(c), owner.actor
        )


def run_next(owner: OwnerBuild, *, allow_background_subscription_run: bool) -> dict[str, Any]:
    if allow_background_subscription_run is not True:
        raise KernelDenied("explicit_background_subscription_run_required")
    selection = select_next(owner)
    selected = selection["selected"]
    if selected is None:
        return selection
    # Selection is only a read. The existing controller takes the fleet-wide
    # session lock and revalidates immutable binding/current policy, actual
    # principal, billing, quota, foreground and storage before every claim.
    # A race/denial/failed job returns immediately: never try another item.
    result = BackgroundPlanRunner(owner, selected["item_id"]).run_item(allow_background_subscription_run=True)
    return {**result, "selection": selection, "selected_item_id": selected["item_id"]}
