"""Finite, explicitly reviewed same-contract revisions after confirmed stopped work.

Every prior version's full envelope remains charged. Old tasks/handoffs/results
stay historical; a revision cannot bypass an unresolved claim, widen authority,
renew an expired review in place or automatically retry a native call.
"""

from __future__ import annotations

from datetime import UTC

from panestria.contracts.build import canonical_sha256
from panestria.contracts.plan import PlanProposal, PlanRevisionConsent, ProjectInventory, StoredPlan
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.plan_store import PlanStore
from panestria.kernel.plans import PlanValidator
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.scheduler import FLEET_LOCK
from panestria.kernel.uow import UnitOfWork


class PlanRevisionService:
    def propose(
        self,
        uow: UnitOfWork,
        actor: Actor,
        parent_id: str,
        parent_sha256: str,
        proposal: PlanProposal,
        inventory: ProjectInventory,
        return_proof_sha256: str,
        *,
        maximum_versions: int = 3,
    ) -> StoredPlan:
        store = PlanStore()
        store._transaction(uow)
        if type(maximum_versions) is not int or not 2 <= maximum_versions <= 3:
            raise KernelDenied("plan_repair_limit_invalid")
        proposal = PlanProposal.model_validate(proposal)
        inventory = ProjectInventory.model_validate(inventory)
        if len(proposal.model_dump_json().encode()) > 128 * 1024 or len(inventory.model_dump_json().encode()) > 16384:
            raise KernelDenied("plan_document_limit")
        uow.execute("SELECT pg_advisory_xact_lock(%s,%s)", FLEET_LOCK)
        status, cid, contract = store._goal(uow, actor, proposal.goal_id)
        parent = store.get(uow, actor, parent_id)
        if (
            parent.proposal.goal_id != proposal.goal_id
            or parent.proposal.sha256() != parent_sha256
            or proposal.contract_sha256 != parent.proposal.contract_sha256
            or inventory != parent.inventory
            or contract.privacy_class != "PUBLIC"
            or contract.budget.max_api_usd != "0"
        ):
            raise KernelDenied("plan_scope_change_requires_new_authorization")
        checked = PlanValidator().validate(actor, proposal, contract, inventory)
        # Replay is historical acknowledgment, not renewed consent or dispatch.
        prior = uow.execute("SELECT id::text FROM panestria.build_plan WHERE id=%s", (proposal.plan_id,)).fetchone()
        if prior:
            old = store.get(uow, actor, proposal.plan_id)
            consent = old.consent
            if (
                old.proposal != proposal
                or old.inventory != inventory
                or not isinstance(consent, PlanRevisionConsent)
                or consent.parent_sha256 != parent_sha256
                or consent.return_proof_sha256 != return_proof_sha256
                or consent.maximum_versions != maximum_versions
            ):
                raise KernelDenied("plan_revision_replay_conflict")
            return old
        family = uow.execute(
            "SELECT id::text FROM panestria.build_plan WHERE goal_id=%s ORDER BY version",
            (proposal.goal_id,),
        ).fetchall()
        if not family or family[-1] != (parent_id,):
            raise KernelDenied("plan_parent_superseded")
        if status not in {"CREATED", "ACTIVE"}:
            raise KernelDenied("plan_goal_not_active")
        if isinstance(parent.consent, PlanRevisionConsent) and parent.consent.maximum_versions != maximum_versions:
            raise KernelDenied("plan_repair_limit_change_requires_authorization")
        version = parent.version + 1
        if version > maximum_versions or len(family) != parent.version:
            raise KernelDenied("plan_repair_limit_exhausted")
        prior_plans = [store.get(uow, actor, row[0]) for row in family]
        if any(p.proposal.contract_sha256 != proposal.contract_sha256 or p.inventory != inventory for p in prior_plans):
            raise KernelDenied("plan_scope_change_requires_new_authorization")
        total_wall = sum(p.validation.upper_wall_seconds for p in prior_plans) + checked.upper_wall_seconds
        total_cash = sum(p.validation.upper_api_microusd for p in prior_plans) + checked.upper_api_microusd
        if total_wall > contract.budget.max_wall_seconds or total_cash:
            raise KernelDenied("plan_repair_budget_exhausted")
        proof = uow.execute(
            "SELECT r.proof,r.proof_sha256,c.plan_id::text FROM panestria.build_claim_release r "
            "JOIN panestria.build_worker_claim c ON c.attempt_id=r.attempt_id "
            "JOIN panestria.build_plan p ON p.id=c.plan_id WHERE p.goal_id=%s "
            "AND r.reason='VERIFIED_RETURN' AND r.proof_sha256=%s",
            (proposal.goal_id, return_proof_sha256),
        ).fetchone()
        if (
            proof is None
            or canonical_sha256(proof[0]) != str(proof[1]).strip()
            or proof[0].get("plan_id") != proof[2]
            or (proof[2],) not in family
        ):
            raise KernelDenied("plan_return_proof_unconfirmed")
        tasks = uow.execute(
            "SELECT id::text,state FROM panestria.task WHERE goal_id=%s ORDER BY id FOR UPDATE", (proposal.goal_id,)
        ).fetchall()
        if (
            uow.execute(
                "SELECT 1 FROM panestria.build_active_worker_claim c JOIN panestria.task t ON t.id=c.task_id "
                "WHERE t.goal_id=%s LIMIT 1",
                (proposal.goal_id,),
            ).fetchone()
            or uow.execute(
                "SELECT 1 FROM panestria.worker_invocation i JOIN panestria.task t ON t.id=i.task_id "
                "WHERE t.goal_id=%s AND i.state IN ('CLAIMED','UNKNOWN') LIMIT 1",
                (proposal.goal_id,),
            ).fetchone()
            or uow.execute(
                "SELECT 1 FROM panestria.side_effect s JOIN panestria.task t ON t.id=s.task_id "
                "WHERE t.goal_id=%s AND s.state!='PREPARED' LIMIT 1",
                (proposal.goal_id,),
            ).fetchone()
        ):
            raise KernelDenied("plan_previous_work_unconfirmed")
        terminal = {"COMPLETED", "FAILED", "CANCELLED", "REJECTED"}
        pending = {"CREATED", "READY", "RETRY_WAIT"}
        if any(state not in terminal | pending for _, state in tasks):
            raise KernelDenied("plan_previous_work_unconfirmed")
        if any(
            uow.execute("SELECT 1 FROM panestria.task WHERE id=%s", (n.task_id,)).fetchone() for n in proposal.nodes
        ):
            raise KernelDenied("plan_task_id_conflict")
        # Only undispatched pending tasks are fenced. Active/unknown work above
        # must first complete qualified reconciliation; never free by timeout.
        fenced = []
        for task, state in tasks:
            if state in pending:
                uow.execute(
                    "UPDATE panestria.task SET state='CANCELLING',row_version=row_version+1 WHERE id=%s", (task,)
                )
                uow.execute(
                    "UPDATE panestria.task SET state='CANCELLED',row_version=row_version+1 WHERE id=%s", (task,)
                )
                fenced.append(task)
        expiry = uow.execute("SELECT clock_timestamp()+interval '15 minutes'").fetchone()
        assert expiry is not None
        consent = PlanRevisionConsent(
            plan_sha256=proposal.sha256(),
            contract_sha256=proposal.contract_sha256,
            inventory_sha256=inventory.sha256(),
            policy_ref=contract.autonomy_profile_ref,
            expires_at=expiry[0].astimezone(UTC).isoformat(),
            version=version,
            maximum_versions=maximum_versions,
            parent_sha256=parent_sha256,
            return_proof_sha256=return_proof_sha256,
            cumulative_wall_seconds=total_wall,
            cumulative_api_microusd=0,
        )
        uow.execute(
            "INSERT INTO panestria.build_plan(id,owner_id,project_id,goal_id,contract_id,"
            "version,parent_id,body,inventory,"
            "validation,consent,proposal_sha256,inventory_sha256,effect_digest,expires_at) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s,%s)",
            (
                proposal.plan_id,
                actor.owner_id,
                actor.project_id,
                proposal.goal_id,
                cid,
                version,
                parent_id,
                proposal.model_dump_json(),
                inventory.model_dump_json(),
                checked.model_dump_json(),
                consent.model_dump_json(),
                proposal.sha256(),
                inventory.sha256(),
                consent.sha256(),
                expiry[0],
            ),
        )
        append_event(
            uow,
            goal_id=proposal.goal_id,
            task_id=None,
            actor=actor.owner_id,
            kind="build.plan.revision_proposed",
            payload={
                "plan_id": proposal.plan_id,
                "parent_plan_id": parent_id,
                "version": version,
                "proposal_sha256": proposal.sha256(),
                "return_proof_sha256": return_proof_sha256,
                "cumulative_wall_seconds": total_wall,
                "maximum_versions": maximum_versions,
                "fenced_pending_tasks": fenced,
                "effect_digest": consent.sha256(),
                "execution_authority": "NONE",
            },
        )
        return StoredPlan(
            proposal=proposal,
            inventory=inventory,
            validation=checked,
            consent=consent,
            effect_digest=consent.sha256(),
            version=version,
            parent_sha256=parent_sha256,
            state="PROPOSED",
        )
