"""Bounded coordinator admission over existing immutable events and task state.

The execution controller additionally holds a session advisory lock throughout
its finite run. A crash drops that lock but does not erase canonical claims or
the unfinished coordinator fact. No lease is released by this service.
"""

import json
from datetime import datetime, timedelta
from typing import Any

from panestria.contracts.background import BackgroundBinding
from panestria.contracts.background_run import BackgroundRun
from panestria.contracts.build import canonical_sha256
from panestria.contracts.hardware import HardwareManifest
from panestria.contracts.native_account import BackgroundAccountLink
from panestria.kernel.background import BackgroundWorkService
from panestria.kernel.background_account import BackgroundAccountService
from panestria.kernel.build import BuildEvidenceService, BuildEvidenceStore
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.plan_store import PlanStore
from panestria.kernel.quota import QuotaService
from panestria.kernel.repositories.policy import lock_project
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.scheduler import FLEET_LOCK, Queued, Scheduled, Scheduler
from panestria.kernel.uow import UnitOfWork

BACKGROUND_SESSION_LOCK = (726173, 27)


class BackgroundRunService:
    def __init__(self, accounts: BuildEvidenceStore, evidence: BuildEvidenceService) -> None:
        self.accounts, self.evidence = BackgroundAccountService(accounts), evidence

    def _lock(self, uow: UnitOfWork, actor: Actor) -> None:
        PlanStore()._transaction(uow)
        uow.execute("SELECT pg_advisory_xact_lock(%s,%s)", FLEET_LOCK)
        lock_project(uow, actor)

    def listing(self, uow: UnitOfWork, actor: Actor, item_id: str) -> dict[str, Any]:
        binding = self.accounts.binding(uow, actor, item_id)
        items = []
        for row in self._history(uow, binding):
            run = self._run(row, binding)
            returned = uow.execute(
                "SELECT seq,occurred_at,payload FROM panestria.task_event "
                "WHERE goal_id=%s AND kind='background.run_returned' "
                "AND payload->>'run_sha256'=%s LIMIT 1",
                (binding.goal_id, run.sha256()),
            ).fetchone()
            items.append(
                {
                    "run": run.model_dump(mode="json"),
                    "run_sha256": run.sha256(),
                    "coordinator_status": "RETURN_RECORDED" if returned else "UNCONFIRMED",
                    "returned_at": returned[1].isoformat() if returned else None,
                    "claim_release_authority": "NONE",
                }
            )
        claims = Scheduler().claims(uow, actor, binding.request.plan_id)
        for claim in claims:
            expiry = claim.get("lease_expires_at")
            if isinstance(expiry, datetime):
                claim["lease_expires_at"] = expiry.isoformat()
        return {
            "item_id": item_id,
            "runs": items,
            "claims": claims,
            "execution_authority": "NONE",
        }

    def _history(self, uow: UnitOfWork, binding: BackgroundBinding) -> list[tuple[Any, ...]]:
        rows = uow.execute(
            "SELECT seq,payload FROM panestria.task_event WHERE goal_id=%s AND task_id=%s "
            "AND kind='background.run_started' AND payload->'run'->>'item_id'=%s ORDER BY seq LIMIT 17",
            (binding.goal_id, binding.task_id, binding.request.item_id),
        ).fetchall()
        if len(rows) > 16:
            raise KernelDenied("background_run_history_limit")
        return rows

    def _run(self, row: tuple[Any, ...], binding: BackgroundBinding) -> BackgroundRun:
        try:
            run = BackgroundRun.model_validate_json(json.dumps(row[1]["run"]))
            if run.sha256() != row[1]["run_sha256"] or (
                run.owner_id,
                run.project_id,
                run.item_id,
                run.binding_sha256,
            ) != (binding.owner_id, binding.project_id, binding.request.item_id, binding.sha256()):
                raise ValueError
            return run
        except (ValueError, KeyError, TypeError):
            raise KernelDenied("background_run_record_invalid") from None

    def _current_account(
        self, uow: UnitOfWork, actor: Actor, binding: BackgroundBinding, observation_sha256: str
    ) -> BackgroundAccountLink:
        links = self.accounts._links(uow, binding)
        if not links:
            raise KernelDenied("background_account_not_linked")
        linked = self.accounts._link(links[-1], binding)
        observed = self.accounts.observation(observation_sha256)
        now = uow.execute("SELECT clock_timestamp()").fetchone()
        assert now is not None
        if not observed.observed_at <= now[0] < observed.observed_at + timedelta(seconds=30):
            raise KernelDenied("background_current_auth_observation_required")
        if (
            observed.owner_id,
            observed.project_id,
            observed.account_ref,
            observed.identity_sha256,
            observed.profile_sha256,
            observed.binary_sha256,
        ) != (
            actor.owner_id,
            actor.project_id,
            linked.account_ref,
            linked.identity_sha256,
            linked.profile_sha256,
            linked.binary_sha256,
        ):
            raise KernelDenied("background_current_auth_principal_changed")
        return linked

    def _eligibility(self, uow: UnitOfWork, actor: Actor, binding: BackgroundBinding) -> dict[str, Any]:
        view = BackgroundWorkService().inspect(uow, actor, binding)
        withdrawn = uow.execute(
            "SELECT 1 FROM panestria.task_event WHERE goal_id=%s AND kind='background.withdrawn' "
            "AND payload->>'item_id'=%s LIMIT 1",
            (binding.goal_id, binding.request.item_id),
        ).fetchone()
        if withdrawn:
            raise KernelDenied("background_item_withdrawn")
        reasons = list(view["waiting_reasons"])
        if "goal_already_started_or_requires_owner_inspection" in reasons:
            # Only this controller's previously started plan may continue from
            # independently verified intermediate handoffs. No old claim is adopted.
            if not self._history(uow, binding):
                raise KernelDenied("background_fresh_unstarted_goal_required")
            tasks = uow.execute(
                "SELECT id::text,state FROM panestria.task WHERE goal_id=%s", (binding.goal_id,)
            ).fetchall()
            for task, state in tasks:
                if state in {"CREATED", "READY"}:
                    continue
                if state != "COMPLETED" or task == binding.task_id:
                    raise KernelDenied("background_task_requires_owner_inspection")
                handoff = uow.execute(
                    "SELECT handoff_id::text FROM panestria.build_worker_claim WHERE task_id=%s "
                    "AND released_at IS NOT NULL AND handoff_id IS NOT NULL ORDER BY created_at DESC LIMIT 1",
                    (task,),
                ).fetchone()
                if not handoff:
                    raise KernelDenied("background_dependency_not_verified")
                PlanStore().read_handoff(uow, actor, handoff[0], self.evidence)
            reasons.remove("goal_already_started_or_requires_owner_inspection")
        if reasons:
            raise KernelDenied("background_wait:" + sorted(set(reasons))[0])
        signal = uow.execute(
            "SELECT e.occurred_at FROM panestria.task_event e JOIN panestria.goal g ON g.id=e.goal_id "
            "WHERE g.owner_id=%s AND g.project_id=%s AND e.kind='background.route_limited' "
            "AND e.payload->>'account_ref'=%s ORDER BY e.seq DESC LIMIT 1",
            (actor.owner_id, actor.project_id, binding.request.policy.quota_windows[0].account_ref),
        ).fetchone()
        if signal:
            # A native failure signal is not a numeric balance or a guessed reset.
            # Require newer actual numeric evidence in every overlapping window.
            for window in binding.request.policy.quota_windows:
                views = QuotaService().latest(uow, actor, window)
                if not any(
                    v.freshness == "FRESH"
                    and v.effective_remaining is not None
                    and v.observation.source in {"OWNER_REPORTED", "PROVIDER_REPORTED"}
                    and v.observation.observed_at > signal[0]
                    for v in views
                ):
                    raise KernelDenied("background_route_limit_requires_new_eligibility_evidence")
        return view

    def start(self, uow: UnitOfWork, actor: Actor, item_id: str, observation_sha256: str, run_id: str) -> BackgroundRun:
        self._lock(uow, actor)
        binding = self.accounts.binding(uow, actor, item_id)
        linked = self._current_account(uow, actor, binding, observation_sha256)
        view = self._eligibility(uow, actor, binding)
        # The session lock serializes live controllers; this immutable fact also
        # holds the coordinator after crashes until explicit safe reconciliation.
        active = uow.execute(
            "SELECT 1 FROM panestria.task_event s WHERE s.kind='background.run_started' AND NOT EXISTS "
            "(SELECT 1 FROM panestria.task_event r WHERE r.goal_id=s.goal_id AND r.kind='background.run_returned' "
            "AND r.payload->>'run_sha256'=s.payload->>'run_sha256') LIMIT 1"
        ).fetchone()
        if active:
            raise KernelDenied("background_previous_run_requires_reconciliation")
        history = self._history(uow, binding)
        if len(history) >= 16:
            raise KernelDenied("background_run_history_limit")
        used = 0
        for row in history:
            prior = self._run(row, binding)
            stopped = uow.execute(
                "SELECT occurred_at FROM panestria.task_event WHERE goal_id=%s AND kind='background.run_returned' "
                "AND payload->>'run_sha256'=%s LIMIT 1",
                (binding.goal_id, prior.sha256()),
            ).fetchone()
            if stopped is None:
                raise KernelDenied("background_previous_run_requires_reconciliation")
            used += max(0, int((stopped[0] - prior.started_at).total_seconds()) + 1)
        quota_basis = canonical_sha256(sorted(o["observation_id"] for o in view["quota_observations"]))
        consumed = uow.execute(
            "SELECT 1 FROM panestria.task_event e JOIN panestria.goal g ON g.id=e.goal_id "
            "WHERE g.owner_id=%s AND g.project_id=%s AND e.kind='background.run_started' "
            "AND e.payload->'run'->>'quota_basis_sha256'=%s AND e.payload->'run'->>'item_id'<>%s LIMIT 1",
            (actor.owner_id, actor.project_id, quota_basis, item_id),
        ).fetchone()
        if view["quota_observations"] and consumed:
            raise KernelDenied("background_quota_report_already_consumed_by_another_job")
        now = uow.execute("SELECT clock_timestamp()").fetchone()
        assert now is not None
        billing = binding.request.policy.billing
        assert billing is not None and billing.usage_credits_enabled is False
        remaining = binding.request.policy.maximum_job_wall_seconds - used
        if remaining < 30:
            raise KernelDenied("background_original_job_wall_budget_exhausted")
        run = BackgroundRun(
            run_id=run_id,
            owner_id=actor.owner_id,
            project_id=actor.project_id,
            item_id=item_id,
            binding_sha256=binding.sha256(),
            link_sha256=linked.sha256(),
            account_observation_sha256=observation_sha256,
            identity_sha256=linked.identity_sha256,
            profile_sha256=linked.profile_sha256,
            binary_sha256=linked.binary_sha256,
            quota_basis_sha256=quota_basis,
            started_at=now[0],
            deadline=min(
                now[0] + timedelta(seconds=remaining),
                binding.request.policy.expires_at,
                billing.observed_at + timedelta(seconds=billing.fresh_for_seconds),
            ),
        )
        append_event(
            uow,
            goal_id=binding.goal_id,
            task_id=binding.task_id,
            actor=actor.owner_id,
            kind="background.run_started",
            payload={"run": run.model_dump(mode="json"), "run_sha256": run.sha256()},
        )
        return run

    def claim(
        self, uow: UnitOfWork, actor: Actor, run: BackgroundRun, observation_sha256: str, capacity: HardwareManifest
    ) -> Scheduled | Queued:
        self._lock(uow, actor)
        binding = self.accounts.binding(uow, actor, run.item_id)
        rows = self._history(uow, binding)
        if not rows or self._run(rows[-1], binding) != run:
            raise KernelDenied("background_run_not_current")
        if uow.execute(
            "SELECT 1 FROM panestria.task_event WHERE goal_id=%s AND kind='background.run_returned' "
            "AND payload->>'run_sha256'=%s LIMIT 1",
            (binding.goal_id, run.sha256()),
        ).fetchone():
            raise KernelDenied("background_run_already_returned")
        linked = self._current_account(uow, actor, binding, observation_sha256)
        if linked.sha256() != run.link_sha256:
            raise KernelDenied("background_run_account_review_changed")
        try:
            self._eligibility(uow, actor, binding)
        except KernelDenied as exc:
            return Queued(binding.task_id, exc.code)
        plan = PlanStore().get(uow, actor, binding.request.plan_id)
        now = uow.execute("SELECT clock_timestamp()").fetchone()
        assert now is not None
        # Conservative full-node envelope: never claim a lease that would run
        # past the original aggregate policy or fresh billing-report boundary.
        if (run.deadline - now[0]).total_seconds() < max(n.wall_seconds_per_attempt for n in plan.proposal.nodes):
            return Queued(binding.task_id, "background_wall_or_report_boundary")
        job = Scheduler().claim_ready(uow, actor, binding.request.plan_id, capacity, self.evidence)
        if isinstance(job, Scheduled):
            return job
        return job[0] if job else Queued(binding.task_id, "background_no_ready_task")

    def finish(self, uow: UnitOfWork, actor: Actor, run: BackgroundRun, reason: str) -> dict[str, Any]:
        self._lock(uow, actor)
        binding = self.accounts.binding(uow, actor, run.item_id)
        rows = self._history(uow, binding)
        if not rows or self._run(rows[-1], binding) != run:
            raise KernelDenied("background_run_not_current")
        old = uow.execute(
            "SELECT seq FROM panestria.task_event WHERE goal_id=%s AND kind='background.run_returned' "
            "AND payload->>'run_sha256'=%s LIMIT 1",
            (binding.goal_id, run.sha256()),
        ).fetchone()
        if old:
            return {"event_seq": old[0], "replayed": True}
        if reason not in {"controller_returned", "controller_exception", "reconciled_stopped"}:
            raise KernelDenied("background_return_reason_invalid")
        seq = append_event(
            uow,
            goal_id=binding.goal_id,
            task_id=binding.task_id,
            actor=actor.owner_id,
            kind="background.run_returned",
            payload={"run_sha256": run.sha256(), "reason": reason, "claim_release_authority": "NONE"},
        )
        return {"event_seq": seq, "replayed": False, "claim_release_authority": "NONE"}

    def record_limit(self, uow: UnitOfWork, actor: Actor, run: BackgroundRun) -> None:
        self._lock(uow, actor)
        binding = self.accounts.binding(uow, actor, run.item_id)
        append_event(
            uow,
            goal_id=binding.goal_id,
            task_id=binding.task_id,
            actor=actor.owner_id,
            kind="background.route_limited",
            payload={
                "run_sha256": run.sha256(),
                "account_ref": binding.request.policy.quota_windows[0].account_ref,
                "source": "NATIVE_CLI_FAILURE_NOT_A_NUMERIC_BALANCE",
                "remaining": None,
                "resets_at": None,
            },
        )

    def reconcile(self, uow: UnitOfWork, actor: Actor, item_id: str, run_sha256: str) -> dict[str, Any]:
        # Caller holds the workstation session lock: a current controller cannot
        # be between claims while this safe-stop proof is recorded.
        self._lock(uow, actor)
        binding = self.accounts.binding(uow, actor, item_id)
        history = self._history(uow, binding)
        if not history:
            raise KernelDenied("not_found")
        run = self._run(history[-1], binding)
        if run.sha256() != run_sha256:
            raise KernelDenied("background_run_changed")
        unsafe = uow.execute(
            "SELECT EXISTS(SELECT 1 FROM panestria.build_active_worker_claim WHERE plan_id=%s) OR "
            "EXISTS(SELECT 1 FROM panestria.worker_invocation i JOIN panestria.task t ON t.id=i.task_id "
            "WHERE t.goal_id=%s AND i.state<>'RETURNED')",
            (binding.request.plan_id, binding.goal_id),
        ).fetchone()
        if unsafe != (False,):
            raise KernelDenied("background_unconfirmed_invocation_or_claim_retained")
        return self.finish(uow, actor, run, "reconciled_stopped")
