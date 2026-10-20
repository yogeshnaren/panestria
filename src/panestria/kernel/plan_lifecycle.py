"""Plan-wide cancellation and proof-bound reservation release, never process cleanup.

Unknown native processes retain capacity. No lease timeout, owner guess, deletion
or provider retry can stand in for an acknowledged no-dispatch/final-merge proof.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from panestria.contracts.build import canonical_sha256
from panestria.contracts.plan import StoredPlan
from panestria.contracts.task import ALLOWED_TRANSITIONS
from panestria.kernel.build import BuildEvidenceService
from panestria.kernel.effects import DispatchClaim
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.plan_store import PlanStore
from panestria.kernel.repositories.policy import lock_project
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.scheduler import FLEET_LOCK
from panestria.kernel.uow import UnitOfWork


@dataclass(frozen=True)
class PlanCancellation:
    status: str
    plan_id: str
    cancelled_tasks: int
    stopping_tasks: int
    held_claims: int


class PlanLifecycle:
    def _locked(self, uow: UnitOfWork, actor: Actor, plan_id: str) -> StoredPlan:
        PlanStore()._transaction(uow)
        uow.execute("SELECT pg_advisory_xact_lock(%s,%s)", FLEET_LOCK)
        lock_project(uow, actor)
        plan = PlanStore()._read(uow, actor, plan_id)
        if plan.state != "ACCEPTED":
            raise KernelDenied("plan_not_accepted")
        goal = uow.execute(
            "SELECT id FROM panestria.goal WHERE id=%s AND owner_id=%s AND project_id=%s FOR UPDATE",
            (plan.proposal.goal_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if goal is None:
            raise KernelDenied("not_found")
        cid = uow.execute("SELECT contract_id::text FROM panestria.build_plan WHERE id=%s", (plan_id,)).fetchone()
        assert cid is not None
        PlanStore()._members(uow, plan, cid[0])
        uow.execute(
            "SELECT id FROM panestria.task WHERE goal_id=%s ORDER BY id FOR UPDATE", (plan.proposal.goal_id,)
        ).fetchall()
        uow.execute(
            "SELECT c.attempt_id FROM panestria.build_worker_claim c JOIN panestria.task t ON t.id=c.task_id "
            "WHERE t.goal_id=%s ORDER BY c.attempt_id FOR UPDATE OF c",
            (plan.proposal.goal_id,),
        ).fetchall()
        # Historical cancellation must remain possible after policy revocation.
        # This withdraws authority; it neither widens nor revalidates dispatch.
        return plan

    def _release(self, uow: UnitOfWork, attempt_id: str, reason: str, proof: dict[str, object]) -> str:
        digest = canonical_sha256(proof)
        previous = uow.execute(
            "SELECT reason,proof,proof_sha256 FROM panestria.build_claim_release WHERE attempt_id=%s", (attempt_id,)
        ).fetchone()
        if previous:
            if previous != (reason, proof, digest):
                raise KernelDenied("claim_release_conflict")
            return digest
        uow.execute(
            "INSERT INTO panestria.build_claim_release(attempt_id,reason,proof,proof_sha256) "
            "VALUES(%s,%s,%s::jsonb,%s)",
            (attempt_id, reason, json.dumps(proof), digest),
        )
        return digest

    def cancel(
        self,
        uow: UnitOfWork,
        actor: Actor,
        plan_id: str,
        plan_sha256: str,
        *,
        expected_final_version: int | None = None,
    ) -> PlanCancellation:
        plan = self._locked(uow, actor, plan_id)
        if plan.proposal.sha256() != plan_sha256:
            raise KernelDenied("plan_review_changed")
        rows = uow.execute(
            "SELECT id::text,state,row_version FROM panestria.task WHERE goal_id=%s ORDER BY id",
            (plan.proposal.goal_id,),
        ).fetchall()
        goal_status = uow.execute("SELECT status FROM panestria.goal WHERE id=%s", (plan.proposal.goal_id,)).fetchone()
        assert goal_status is not None
        if goal_status[0] in {"COMPLETED", "FAILED", "CANCELLED"}:
            held = uow.execute(
                "SELECT count(*) FROM panestria.build_active_worker_claim c "
                "JOIN panestria.task t ON t.id=c.task_id WHERE t.goal_id=%s",
                (plan.proposal.goal_id,),
            ).fetchone()
            assert held is not None
            return PlanCancellation(
                goal_status[0],
                plan_id,
                sum(s == "CANCELLED" for _, s, _ in rows),
                sum(s == "CANCELLING" for _, s, _ in rows),
                held[0],
            )
        if expected_final_version is not None:
            sources = {d for n in plan.proposal.nodes for d in n.depends_on}
            finals = [n.task_id for n in plan.proposal.nodes if n.task_id not in sources]
            if len(finals) != 1 or not any(t == finals[0] and v == expected_final_version for t, _, v in rows):
                raise KernelDenied("version_conflict")
        changed, releases = [], []
        terminal = {"COMPLETED", "FAILED", "REJECTED", "CANCELLED"}
        for task, state, _ in rows:
            if state in terminal:
                continue
            # Task locks serialize with prepare/claim/finish, including inserts.
            invocations = uow.execute(
                "SELECT state FROM panestria.worker_invocation WHERE task_id=%s FOR UPDATE", (task,)
            ).fetchall()
            effects = uow.execute(
                "SELECT state FROM panestria.side_effect WHERE task_id=%s FOR UPDATE", (task,)
            ).fetchall()
            never_dispatched = all(r[0] == "PREPARED" for r in invocations) and all(r[0] == "PREPARED" for r in effects)
            target = "CANCELLED" if never_dispatched else "CANCELLING"
            if state != "CANCELLING":
                if (state, "CANCELLING") not in ALLOWED_TRANSITIONS:
                    raise KernelDenied("illegal_transition")
                uow.execute(
                    "UPDATE panestria.task SET state='CANCELLING',row_version=row_version+1 WHERE id=%s", (task,)
                )
            if target == "CANCELLED":
                uow.execute(
                    "UPDATE panestria.task SET state='CANCELLED',row_version=row_version+1 WHERE id=%s", (task,)
                )
            uow.execute(
                "UPDATE panestria.task_attempt SET status=%s,finished_at=clock_timestamp() "
                "WHERE task_id=%s AND status IN ('PENDING','RUNNING','CANCELLING') AND status!=%s",
                (target, task, target),
            )
            if state != target:
                changed.append({"task_id": task, "from": state, "to": target})
            if never_dispatched:
                claims = uow.execute(
                    "SELECT attempt_id::text,lease_epoch FROM panestria.build_active_worker_claim WHERE task_id=%s",
                    (task,),
                ).fetchall()
                for attempt, epoch in claims:
                    proof = {
                        "plan_id": plan_id,
                        "plan_sha256": plan_sha256,
                        "task_id": task,
                        "attempt_id": attempt,
                        "lease_epoch": epoch,
                        "task_state": "CANCELLED",
                        "reason": "NO_DISPATCH",
                        "claimed_or_unknown_invocations": 0,
                        "dispatched_effects": 0,
                    }
                    releases.append(self._release(uow, attempt, "NO_DISPATCH", proof))
        current = uow.execute("SELECT state FROM panestria.task WHERE goal_id=%s", (plan.proposal.goal_id,)).fetchall()
        held = uow.execute(
            "SELECT count(*) FROM panestria.build_active_worker_claim c "
            "JOIN panestria.task t ON t.id=c.task_id WHERE t.goal_id=%s",
            (plan.proposal.goal_id,),
        ).fetchone()
        assert held is not None
        stopped = all(r[0] in terminal for r in current) and held[0] == 0
        if stopped:
            uow.execute(
                "UPDATE panestria.goal SET status='CANCELLED' WHERE id=%s AND status IN ('CREATED','ACTIVE')",
                (plan.proposal.goal_id,),
            )
        if changed or releases:
            append_event(
                uow,
                goal_id=plan.proposal.goal_id,
                task_id=None,
                actor=actor.owner_id,
                kind="build.plan.cancelled" if stopped else "build.plan.cancel_requested",
                payload={
                    "plan_id": plan_id,
                    "transitions": changed,
                    "release_proofs": releases,
                    "held_claims": held[0],
                },
            )
        return PlanCancellation(
            "CANCELLED" if stopped else "CANCEL_REQUESTED",
            plan_id,
            sum(r[0] == "CANCELLED" for r in current),
            sum(r[0] == "CANCELLING" for r in current),
            held[0],
        )

    def release_final(
        self,
        uow: UnitOfWork,
        actor: Actor,
        plan_id: str,
        task_id: str,
        evidence_sha256: str,
        effect_id: str,
        evidence: BuildEvidenceService,
    ) -> str:
        plan = self._locked(uow, actor, plan_id)
        dependencies = {d for n in plan.proposal.nodes for d in n.depends_on}
        finals = {n.task_id for n in plan.proposal.nodes} - dependencies
        if finals != {task_id}:
            raise KernelDenied("integration_final_task_required")
        task = uow.execute("SELECT state,lease_epoch FROM panestria.task WHERE id=%s", (task_id,)).fetchone()
        if task is None or task[0] != "COMPLETED":
            raise KernelDenied("confirmed_final_completion_required")
        # Release acknowledges a past physical effect; a later policy/contract
        # change must not turn this into fresh dispatch authorization or hide it.
        effect = uow.execute(
            "SELECT state,external_ref,dispatch_epoch,target,request_ref,request_hash,classification "
            "FROM panestria.side_effect WHERE id=%s AND task_id=%s FOR UPDATE",
            (effect_id, task_id),
        ).fetchone()
        if effect is None or effect[0] != "SUCCEEDED":
            raise KernelDenied("merge_not_confirmed")
        past = DispatchClaim(effect_id, task_id, effect[2], effect[3], effect[4], str(effect[5]).strip(), effect[6])
        bundle = evidence.historical_effect(uow, actor, past)
        if (
            bundle.sha256() != evidence_sha256
            or not bundle.passed()
            or bundle.contract_sha256 != plan.proposal.contract_sha256
            or bundle.base_commit != plan.inventory.base_commit
            or task[1] != bundle.lease_epoch
            or effect[1] != f"git-effect:{effect_id}:{bundle.candidate_commit}:{evidence_sha256}"
        ):
            raise KernelDenied("final_release_evidence_unconfirmed")
        claim = uow.execute(
            "SELECT lease_epoch FROM panestria.build_worker_claim WHERE plan_id=%s AND task_id=%s AND attempt_id=%s",
            (plan_id, task_id, bundle.attempt_id),
        ).fetchone()
        if claim != (bundle.lease_epoch,):
            raise KernelDenied("plan_claim_unconfirmed")
        proof = {
            "plan_id": plan_id,
            "plan_sha256": plan.proposal.sha256(),
            "task_id": task_id,
            "attempt_id": bundle.attempt_id,
            "lease_epoch": bundle.lease_epoch,
            "reason": "VERIFIED_FINAL",
            "evidence_sha256": evidence_sha256,
            "effect_id": effect_id,
        }
        prior = uow.execute(
            "SELECT 1 FROM panestria.build_claim_release WHERE attempt_id=%s", (bundle.attempt_id,)
        ).fetchone()
        digest = self._release(uow, bundle.attempt_id, "VERIFIED_FINAL", proof)
        if prior is None:
            append_event(
                uow,
                goal_id=plan.proposal.goal_id,
                task_id=task_id,
                actor=actor.owner_id,
                kind="build.plan.final_capacity_released",
                payload={"proof_sha256": digest},
            )
        return digest
