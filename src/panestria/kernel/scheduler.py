"""Caller-owned durable admission for accepted plans, not worker dispatch authority.

Every method takes the fleet lock before project/goal/task locks. A claim remains
occupied after expiry, cancellation or an unknown process outcome. Only a current
verified intermediate handoff releases it here; no automatic retry or fallback.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from panestria.contracts.build import canonical_sha256
from panestria.contracts.hardware import HardwareManifest
from panestria.contracts.plan import PlanNode, StoredPlan
from panestria.contracts.policy import PolicyRequest
from panestria.kernel.build import BuildEvidenceService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.leases import AttemptLease, LeaseService
from panestria.kernel.plan_scope import task_plan_scope
from panestria.kernel.plan_store import PlanStore
from panestria.kernel.repositories.policy import current_policy
from panestria.kernel.repositories.tasks import append_event, lock_task
from panestria.kernel.uow import UnitOfWork
from panestria.policy.engine import PolicyEngine
from panestria.resources.hardware import PROBE_SHA256

# Same Postgres, one workstation. Neither a process-local semaphore nor a lease
# timeout can enforce the cap across independent controller processes/restarts.
FLEET_LOCK = (726173, 26)


@dataclass(frozen=True)
class Queued:
    task_id: str
    reason: str


@dataclass(frozen=True)
class Scheduled:
    plan_id: str
    lease: AttemptLease
    hardware_sha256: str
    dispatch_authority: str = "NONE"


class Scheduler:
    def _plan(self, uow: UnitOfWork, actor: Actor, plan_id: str) -> StoredPlan:
        PlanStore()._transaction(uow)
        uow.execute("SELECT pg_advisory_xact_lock(%s,%s)", FLEET_LOCK)
        plan = PlanStore().get(uow, actor, plan_id)
        if plan.state != "ACCEPTED":
            raise KernelDenied("plan_not_accepted")
        goal = uow.execute("SELECT status FROM panestria.goal WHERE id=%s", (plan.proposal.goal_id,)).fetchone()
        if goal is None or goal[0] not in {"CREATED", "ACTIVE"}:
            raise KernelDenied("plan_goal_not_active")
        # Prelock every member in stable order before any event allocation.
        for node in sorted(plan.proposal.nodes, key=lambda n: n.task_id):
            lock_task(uow, actor.owner_id, actor.project_id, node.task_id)
        return plan

    def claims(self, uow: UnitOfWork, actor: Actor, plan_id: str) -> list[dict[str, object]]:
        # Historical inspection remains available after revocation/cancellation.
        # It neither revalidates dispatch nor changes/releases a reservation.
        PlanStore()._read(uow, actor, plan_id)
        rows = uow.execute(
            "SELECT c.attempt_id::text,c.task_id::text,c.lease_epoch,c.released_at IS NULL,"
            "a.status,a.lease_expires_at,c.handoff_id::text,"
            "(SELECT count(*) FROM panestria.worker_invocation i WHERE i.attempt_id=c.attempt_id "
            "AND i.state!='RETURNED') FROM panestria.build_worker_claim c "
            "JOIN panestria.task_attempt a ON a.id=c.attempt_id WHERE c.plan_id=%s ORDER BY c.created_at,c.attempt_id",
            (plan_id,),
        ).fetchall()
        keys = (
            "attempt_id",
            "task_id",
            "lease_epoch",
            "capacity_held",
            "attempt_status",
            "lease_expires_at",
            "handoff_id",
            "unconfirmed_invocations",
        )
        return [dict(zip(keys, row, strict=True)) for row in rows]

    def _reason(
        self, uow: UnitOfWork, actor: Actor, plan: StoredPlan, node: PlanNode, evidence: BuildEvidenceService
    ) -> str:
        scope = task_plan_scope(uow, actor, node.task_id)
        assert scope is not None
        task = lock_task(uow, actor.owner_id, actor.project_id, node.task_id)
        assert task is not None
        if task[1] not in {"CREATED", "READY", "RETRY_WAIT"}:
            return "task_" + task[1].lower()
        if set(node.capabilities) - {"scoped-file-edit", "scoped-bash", "trusted-test-runner"}:
            return "worker_resource_profile_unqualified"
        if node.api_microusd_per_attempt != 0:
            return "paid_dispatch_not_admitted"
        retry = uow.execute(
            "SELECT retry_at IS NULL OR retry_at<=clock_timestamp(),"
            " (SELECT count(*) FROM panestria.task_attempt WHERE task_id=t.id)<max_attempts "
            "FROM panestria.task t WHERE id=%s",
            (node.task_id,),
        ).fetchone()
        if retry != (True, True):
            return "retry_not_due_or_attempts_exhausted"
        for dependency in node.depends_on:
            completed = uow.execute(
                "SELECT c.handoff_id::text FROM panestria.build_worker_claim c "
                "JOIN panestria.task t ON t.id=c.task_id AND t.lease_epoch=c.lease_epoch "
                "WHERE c.task_id=%s AND c.released_at IS NOT NULL AND t.state='COMPLETED'",
                (dependency,),
            ).fetchone()
            if completed is None:
                return "dependency_not_verified"
            PlanStore().read_handoff(uow, actor, completed[0], evidence)
        active = uow.execute(
            "SELECT plan_id::text,task_id::text,worker_ref FROM panestria.build_worker_claim WHERE released_at IS NULL"
        ).fetchall()
        if any(row[1] == node.task_id for row in active):
            return "claim_unreconciled"
        if len(active) >= 2:
            return "fleet_limit"
        same_plan = [r for r in active if r[0] == plan.proposal.plan_id]
        if len(same_plan) >= plan.inventory.maximum_parallel:
            return "plan_parallel_limit"
        worker = next(w for w in plan.inventory.workers if w.worker_ref == node.worker_ref)
        if sum(r[2] == node.worker_ref for r in active) >= worker.maximum_parallel:
            return "worker_parallel_limit"
        nodes = {n.task_id: n for n in plan.proposal.nodes}
        for _, task_id, _ in same_plan:
            if any(
                a == b or a.startswith(b + "/") or b.startswith(a + "/")
                for a in node.paths
                for b in nodes[task_id].paths
            ):
                return "path_conflict"
        policy = current_policy(uow, actor)
        decision = PolicyEngine().authorize(
            PolicyRequest(
                owner_id=actor.owner_id,
                project_id=actor.project_id,
                action="edit",
                label=plan.proposal.privacy_class,
                destination="local",
                effect_digest=scope.sha256(),
            ),
            policy,
        )
        return "ready" if decision.outcome == "PERMIT" else "current_edit_policy_denied"

    def inspect(
        self, uow: UnitOfWork, actor: Actor, plan_id: str, evidence: BuildEvidenceService
    ) -> tuple[Queued, ...]:
        plan = self._plan(uow, actor, plan_id)
        return tuple(Queued(n.task_id, self._reason(uow, actor, plan, n, evidence)) for n in plan.proposal.nodes)

    def claim_ready(
        self, uow: UnitOfWork, actor: Actor, plan_id: str, capacity: HardwareManifest, evidence: BuildEvidenceService
    ) -> Scheduled | tuple[Queued, ...]:
        plan = self._plan(uow, actor, plan_id)
        waiting = tuple(Queued(n.task_id, self._reason(uow, actor, plan, n, evidence)) for n in plan.proposal.nodes)
        node = next(
            (n for n, status in zip(plan.proposal.nodes, waiting, strict=True) if status.reason == "ready"), None
        )
        if node is None:
            return waiting
        # No caller-selected larger footprint or simulated preset can widen the
        # fixed CPU-only envelope. Runtime certificates remain a dispatch check.
        capacity = HardwareManifest.model_validate_json(capacity.model_dump_json())
        now = uow.execute("SELECT clock_timestamp()").fetchone()
        assert now is not None
        observed = capacity.observed_at
        if (
            capacity.simulated
            or capacity.preset is not None
            or capacity.probe_sha256 != PROBE_SHA256
            or observed.tzinfo is None
            or not 0 <= (now[0] - observed).total_seconds() <= 30
        ):
            raise KernelDenied("fresh_actual_capacity_required")
        count = uow.execute("SELECT count(*) FROM panestria.build_worker_claim WHERE released_at IS NULL").fetchone()
        assert count is not None
        workers = count[0] + 1
        if (
            capacity.on_ac_power is not True
            or capacity.thermal_state == "HOT"
            or capacity.logical_cores is None
            or capacity.logical_cores < 2 * workers + 2
            or capacity.ram_available_gib is None
            or capacity.ram_available_gib < 2.5 * workers + 2.0
            or capacity.disk_free_gib is None
            or capacity.disk_free_gib < workers + 2.0
        ):
            return tuple(
                Queued(s.task_id, "foreground_capacity_wait" if s.reason == "ready" else s.reason) for s in waiting
            )
        task = lock_task(uow, actor.owner_id, actor.project_id, node.task_id)
        assert task is not None
        if task[1] == "CREATED":
            uow.execute(
                "UPDATE panestria.task SET state='VALIDATING',row_version=row_version+1 WHERE id=%s",
                (node.task_id,),
            )
            uow.execute(
                "UPDATE panestria.task SET state='READY',row_version=row_version+1 WHERE id=%s", (node.task_id,)
            )
        version = task[2] + (2 if task[1] == "CREATED" else 0)
        lease = LeaseService().acquire(
            uow,
            actor,
            node.task_id,
            node.worker_ref,
            version,
            ttl_seconds=node.wall_seconds_per_attempt,
            emit_event=False,
        )
        hardware = capacity.model_dump(mode="json")
        digest = canonical_sha256(hardware)
        uow.execute(
            "INSERT INTO panestria.build_worker_claim"
            "(attempt_id,plan_id,task_id,lease_epoch,worker_ref,hardware,hardware_sha256) "
            "VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s)",
            (lease.attempt_id, plan_id, node.task_id, lease.epoch, node.worker_ref, json.dumps(hardware), digest),
        )
        append_event(
            uow,
            goal_id=plan.proposal.goal_id,
            task_id=node.task_id,
            actor=actor.owner_id,
            kind="build.scheduler.claimed",
            payload={
                "attempt_id": lease.attempt_id,
                "epoch": lease.epoch,
                "plan_id": plan_id,
                "hardware_sha256": digest,
                "previous_state": task[1],
                "dispatch_authority": "NONE",
                "api_cash_microusd": 0,
                "quota_remaining": None,
                "quota_source": "unknown",
            },
        )
        return Scheduled(plan_id, lease, digest)

    def complete_node(
        self, uow: UnitOfWork, actor: Actor, plan_id: str, handoff_id: str, evidence: BuildEvidenceService
    ) -> None:
        plan = self._plan(uow, actor, plan_id)
        handoff = PlanStore().read_handoff(uow, actor, handoff_id, evidence)
        task_id = handoff.submission.task_id
        scope = task_plan_scope(uow, actor, task_id)
        if scope is None or scope.integration or scope.plan_id != plan_id:
            raise KernelDenied("intermediate_plan_node_required")
        claim = uow.execute(
            "SELECT lease_epoch,released_at,handoff_id::text FROM panestria.build_worker_claim "
            "WHERE attempt_id=%s AND task_id=%s AND plan_id=%s FOR UPDATE",
            (handoff.attempt_id, task_id, plan_id),
        ).fetchone()
        if claim is None or claim[0] != handoff.lease_epoch:
            raise KernelDenied("plan_claim_unconfirmed")
        if claim[1] is not None:
            if claim[2] != handoff_id:
                raise KernelDenied("plan_completion_conflict")
            return
        task = lock_task(uow, actor.owner_id, actor.project_id, task_id)
        assert task is not None
        if task[1] != "VERIFYING" or task[3] != handoff.lease_epoch:
            raise KernelDenied("plan_node_not_verified")
        if uow.execute(
            "SELECT 1 FROM panestria.worker_invocation WHERE attempt_id=%s AND state!='RETURNED' LIMIT 1",
            (handoff.attempt_id,),
        ).fetchone():
            raise KernelDenied("invocations_unconfirmed")
        uow.execute(
            "UPDATE panestria.task SET state='COMPLETED',row_version=row_version+1,"
            "updated_at=clock_timestamp() WHERE id=%s",
            (task_id,),
        )
        uow.execute(
            "UPDATE panestria.build_worker_claim SET released_at=clock_timestamp(),handoff_id=%s WHERE attempt_id=%s",
            (handoff_id, handoff.attempt_id),
        )
        append_event(
            uow,
            goal_id=plan.proposal.goal_id,
            task_id=task_id,
            actor=actor.owner_id,
            kind="build.scheduler.node_completed",
            payload={
                "handoff_id": handoff_id,
                "handoff_sha256": handoff.sha256(),
                "attempt_id": handoff.attempt_id,
                "goal_completion_authority": "NONE",
            },
        )
