"""Canonical immutable plans, exact owner consent and trusted-evidence handoffs.

The caller owns the same-Postgres transaction. Accepting a plan creates CREATED
canonical task rows only; it neither authorizes a worker nor completes a task.
"""

from __future__ import annotations

import json
from datetime import datetime

from psycopg.pq import TransactionStatus

from panestria.contracts.goal import GoalContract, contract_sha256, load_contract
from panestria.contracts.plan import (
    HandoffSubmission,
    PlanConsent,
    PlanProposal,
    ProjectInventory,
    RetainedHandoff,
    StoredPlan,
    ValidatedDAG,
)
from panestria.contracts.policy import PolicyRequest
from panestria.kernel.build import BuildEvidenceService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.plans import PlanValidator
from panestria.kernel.repositories.policy import current_policy, lock_project
from panestria.kernel.repositories.tasks import append_event, lock_task
from panestria.kernel.uow import UnitOfWork
from panestria.policy.engine import PolicyEngine


class PlanStore:
    def _transaction(self, uow: UnitOfWork) -> None:
        if uow.connection.autocommit and uow.connection.info.transaction_status != TransactionStatus.INTRANS:
            raise KernelDenied("plan_caller_transaction_required")

    def _goal(self, uow: UnitOfWork, actor: Actor, goal: str) -> tuple[str, str, GoalContract]:
        self._transaction(uow)
        lock_project(uow, actor)
        row = uow.execute(
            "SELECT status FROM panestria.goal WHERE id=%s AND owner_id=%s AND project_id=%s FOR UPDATE",
            (goal, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        record = uow.execute(
            "SELECT id::text,body,sha256 FROM panestria.goal_contract WHERE goal_id=%s ORDER BY version DESC LIMIT 1",
            (goal,),
        ).fetchone()
        if record is None:
            raise KernelDenied("plan_contract_missing")
        contract = load_contract(record[1])
        if (contract.owner_id, contract.project_id, contract.goal_id) != (
            actor.owner_id,
            actor.project_id,
            goal,
        ) or contract_sha256(contract) != str(record[2]).strip():
            raise KernelDenied("plan_contract_unconfirmed")
        policy = current_policy(uow, actor)
        ref = f"project-policy:{policy.version}:{policy.sha256()}"
        if contract.autonomy_profile_ref != ref or contract.trust_profile_id != policy.trust.profile:
            raise KernelDenied("plan_policy_changed")
        decision = PolicyEngine().authorize(
            PolicyRequest(
                owner_id=actor.owner_id,
                project_id=actor.project_id,
                action="read",
                label=contract.privacy_class,
                destination="local",
                effect_digest=contract_sha256(contract),
            ),
            policy,
        )
        if decision.outcome != "PERMIT":
            raise KernelDenied("plan_local_read_denied")
        return str(row[0]), str(record[0]), contract

    def _read(self, uow: UnitOfWork, actor: Actor, identifier: str) -> StoredPlan:
        row = uow.execute(
            "SELECT body,inventory,validation,consent,effect_digest,version,parent_id::text,"
            "proposal_sha256,inventory_sha256,expires_at,"
            "EXISTS(SELECT 1 FROM panestria.build_plan_acceptance a WHERE a.plan_id=p.id) "
            "FROM panestria.build_plan p WHERE id=%s AND owner_id=%s AND project_id=%s",
            (identifier, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        proposal = PlanProposal.model_validate_json(json.dumps(row[0]))
        inventory = ProjectInventory.model_validate_json(json.dumps(row[1]))
        validation = ValidatedDAG.model_validate_json(json.dumps(row[2]))
        consent = PlanConsent.model_validate_json(json.dumps(row[3]))
        if (
            proposal.sha256() != str(row[7]).strip()
            or inventory.sha256() != str(row[8]).strip()
            or consent.sha256() != str(row[4]).strip()
            or consent.plan_sha256 != proposal.sha256()
            or consent.inventory_sha256 != inventory.sha256()
            or consent.contract_sha256 != proposal.contract_sha256
            or consent.policy_ref == ""
            or datetime.fromisoformat(consent.expires_at) != row[9]
        ):
            raise KernelDenied("plan_record_unconfirmed")
        parent = None
        if row[6] is not None:
            parent_row = uow.execute(
                "SELECT proposal_sha256 FROM panestria.build_plan WHERE id=%s AND goal_id=%s",
                (row[6], proposal.goal_id),
            ).fetchone()
            if parent_row is None:
                raise KernelDenied("plan_parent_unconfirmed")
            parent = str(parent_row[0]).strip()
        return StoredPlan(
            proposal=proposal,
            inventory=inventory,
            validation=validation,
            consent=consent,
            effect_digest=consent.sha256(),
            version=row[5],
            parent_sha256=parent,
            state="ACCEPTED" if row[10] else "PROPOSED",
        )

    def get(self, uow: UnitOfWork, actor: Actor, identifier: str) -> StoredPlan:
        hint = uow.execute(
            "SELECT goal_id::text FROM panestria.build_plan WHERE id=%s AND owner_id=%s AND project_id=%s",
            (identifier, actor.owner_id, actor.project_id),
        ).fetchone()
        if hint is None:
            raise KernelDenied("not_found")
        _, cid, contract = self._goal(uow, actor, hint[0])
        # Reread after project/goal locks: a concurrent acceptance cannot leave
        # this caller with the pre-lock PROPOSED snapshot.
        plan = self._read(uow, actor, identifier)
        checked = PlanValidator().validate(actor, plan.proposal, contract, plan.inventory)
        if checked != plan.validation:
            raise KernelDenied("plan_validation_unconfirmed")
        if plan.state == "ACCEPTED":
            acceptance = uow.execute(
                "SELECT effect_digest,owner_id::text,project_id::text,accepted_by::text "
                "FROM panestria.build_plan_acceptance WHERE plan_id=%s",
                (identifier,),
            ).fetchone()
            if acceptance != (plan.effect_digest, actor.owner_id, actor.project_id, actor.owner_id):
                raise KernelDenied("plan_acceptance_unconfirmed")
            self._members(uow, plan, cid)
        return plan

    def prepare(self, uow: UnitOfWork, actor: Actor, proposal: PlanProposal, inventory: ProjectInventory) -> StoredPlan:
        proposal = PlanProposal.model_validate(proposal)
        inventory = ProjectInventory.model_validate(inventory)
        if len(proposal.model_dump_json().encode()) > 128 * 1024 or len(inventory.model_dump_json().encode()) > 16384:
            raise KernelDenied("plan_document_limit")
        status, cid, contract = self._goal(uow, actor, proposal.goal_id)
        validation = PlanValidator().validate(actor, proposal, contract, inventory)
        prior = uow.execute(
            "SELECT id::text FROM panestria.build_plan WHERE goal_id=%s ORDER BY version DESC LIMIT 1",
            (proposal.goal_id,),
        ).fetchone()
        if prior:
            plan = self.get(uow, actor, prior[0])
            if plan.proposal == proposal and plan.inventory == inventory:
                return plan
            # Approved revisions/finite repair are a separate admission path.
            raise KernelDenied("plan_revision_not_admitted")
        if status not in {"CREATED", "ACTIVE"}:
            raise KernelDenied("plan_goal_not_active")
        expiry = uow.execute("SELECT clock_timestamp()+interval '15 minutes'").fetchone()
        assert expiry is not None
        consent = PlanConsent(
            plan_sha256=proposal.sha256(),
            contract_sha256=proposal.contract_sha256,
            inventory_sha256=inventory.sha256(),
            policy_ref=contract.autonomy_profile_ref,
            expires_at=expiry[0].isoformat(),
        )
        uow.execute(
            "INSERT INTO panestria.build_plan(id,owner_id,project_id,goal_id,contract_id,version,body,inventory,"
            "validation,consent,proposal_sha256,inventory_sha256,effect_digest,expires_at) "
            "VALUES(%s,%s,%s,%s,%s,1,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s,%s)",
            (
                proposal.plan_id,
                actor.owner_id,
                actor.project_id,
                proposal.goal_id,
                cid,
                proposal.model_dump_json(),
                inventory.model_dump_json(),
                validation.model_dump_json(),
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
            kind="build.plan.proposed",
            payload={
                "plan_id": proposal.plan_id,
                "proposal_sha256": proposal.sha256(),
                "effect_digest": consent.sha256(),
            },
        )
        return StoredPlan(
            proposal=proposal,
            inventory=inventory,
            validation=validation,
            consent=consent,
            effect_digest=consent.sha256(),
            version=1,
            state="PROPOSED",
        )

    def accept(self, uow: UnitOfWork, actor: Actor, identifier: str, digest: str, *, accept_plan: bool) -> StoredPlan:
        if accept_plan is not True:
            raise KernelDenied("explicit_plan_acceptance_required")
        plan = self.get(uow, actor, identifier)
        status, cid, contract = self._goal(uow, actor, plan.proposal.goal_id)
        if digest != plan.effect_digest or plan.consent.policy_ref != contract.autonomy_profile_ref:
            raise KernelDenied("plan_review_changed")
        if plan.state == "ACCEPTED":
            self._members(uow, plan, cid)
            return plan
        fresh = uow.execute(
            "SELECT expires_at>clock_timestamp() FROM panestria.build_plan WHERE id=%s", (identifier,)
        ).fetchone()
        if fresh != (True,) or status not in {"CREATED", "ACTIVE"}:
            raise KernelDenied("plan_review_expired_or_inactive")
        if any(
            uow.execute("SELECT 1 FROM panestria.task WHERE id=%s", (n.task_id,)).fetchone()
            for n in plan.proposal.nodes
        ):
            raise KernelDenied("plan_task_id_conflict")
        uow.execute(
            "INSERT INTO panestria.build_plan_acceptance(plan_id,goal_id,contract_id,owner_id,project_id,"
            "accepted_by,effect_digest) VALUES(%s,%s,%s,%s,%s,%s,%s)",
            (identifier, plan.proposal.goal_id, cid, actor.owner_id, actor.project_id, actor.owner_id, digest),
        )
        for node in plan.proposal.nodes:
            uow.execute(
                "INSERT INTO panestria.task(id,goal_id,contract_id,name,state,max_attempts) "
                "VALUES(%s,%s,%s,%s,'CREATED',%s)",
                (node.task_id, plan.proposal.goal_id, cid, "Plan node " + node.task_id, node.attempts),
            )
            uow.execute(
                "INSERT INTO panestria.build_plan_task(plan_id,task_id,goal_id,contract_id,node_sha256) "
                "VALUES(%s,%s,%s,%s,%s)",
                (identifier, node.task_id, plan.proposal.goal_id, cid, node.sha256()),
            )
        for node in plan.proposal.nodes:
            for dependency in node.depends_on:
                uow.execute(
                    "INSERT INTO panestria.task_dependency(task_id,depends_on) VALUES(%s,%s)",
                    (node.task_id, dependency),
                )
        append_event(
            uow,
            goal_id=plan.proposal.goal_id,
            task_id=None,
            actor=actor.owner_id,
            kind="build.plan.accepted",
            payload={
                "plan_id": identifier,
                "effect_digest": digest,
                "created_tasks": len(plan.proposal.nodes),
                "execution_authority": "NONE",
            },
        )
        return plan.model_copy(update={"state": "ACCEPTED"})

    def _members(self, uow: UnitOfWork, plan: StoredPlan, cid: str) -> None:
        rows = uow.execute(
            "SELECT p.task_id::text,p.node_sha256,t.contract_id::text,t.goal_id::text,t.max_attempts "
            "FROM panestria.build_plan_task p JOIN panestria.task t ON t.id=p.task_id WHERE p.plan_id=%s",
            (plan.proposal.plan_id,),
        ).fetchall()
        if sorted(tuple(str(v).strip() for v in row) for row in rows) != sorted(
            (n.task_id, n.sha256(), cid, plan.proposal.goal_id, str(n.attempts)) for n in plan.proposal.nodes
        ):
            raise KernelDenied("plan_task_membership_unconfirmed")
        edges = uow.execute(
            "SELECT d.task_id::text,d.depends_on::text FROM panestria.task_dependency d "
            "JOIN panestria.build_plan_task p ON p.task_id=d.task_id WHERE p.plan_id=%s",
            (plan.proposal.plan_id,),
        ).fetchall()
        if sorted(edges) != sorted((n.task_id, dependency) for n in plan.proposal.nodes for dependency in n.depends_on):
            raise KernelDenied("plan_dependencies_changed")

    def handoff(
        self, uow: UnitOfWork, actor: Actor, submitted: HandoffSubmission, evidence: BuildEvidenceService
    ) -> RetainedHandoff:
        submitted = HandoffSubmission.model_validate(submitted)
        plan = self.get(uow, actor, submitted.plan_id)
        _, cid, contract = self._goal(uow, actor, plan.proposal.goal_id)
        if plan.state != "ACCEPTED" or plan.consent.policy_ref != contract.autonomy_profile_ref:
            raise KernelDenied("plan_not_accepted_or_current")
        self._members(uow, plan, cid)
        members = {n.task_id: n for n in plan.proposal.nodes}
        if submitted.task_id not in members or set(submitted.next_tasks) - members.keys():
            raise KernelDenied("handoff_scope_mismatch")
        task = lock_task(uow, actor.owner_id, actor.project_id, submitted.task_id)
        if task is None or task[1] not in {"VERIFYING", "WAITING_APPROVAL", "COMPLETED"}:
            raise KernelDenied("handoff_task_not_verified")
        bundle = evidence.current(uow, actor, submitted.task_id, submitted.evidence_sha256)
        node = members[submitted.task_id]
        adapter = uow.execute("SELECT adapter FROM panestria.task_attempt WHERE id=%s", (bundle.attempt_id,)).fetchone()
        if bundle.base_commit != plan.inventory.base_commit or adapter != (node.worker_ref,):
            raise KernelDenied("handoff_worker_or_base_changed")
        worker = next(w for w in plan.inventory.workers if w.worker_ref == node.worker_ref)
        result = RetainedHandoff(
            submission=submitted,
            plan_sha256=plan.proposal.sha256(),
            contract_sha256=plan.proposal.contract_sha256,
            inventory_sha256=plan.inventory.sha256(),
            attempt_id=bundle.attempt_id,
            lease_epoch=bundle.lease_epoch,
            candidate_commit=bundle.candidate_commit,
            candidate_tree=bundle.candidate_tree,
            snapshot_sha256=bundle.snapshot_sha256,
            worker=worker,
        )
        prior = uow.execute(
            "SELECT body,sha256 FROM panestria.build_handoff WHERE task_id=%s AND attempt_id=%s AND lease_epoch=%s",
            (submitted.task_id, bundle.attempt_id, bundle.lease_epoch),
        ).fetchone()
        if prior:
            if (
                RetainedHandoff.model_validate_json(json.dumps(prior[0])) != result
                or str(prior[1]).strip() != result.sha256()
            ):
                raise KernelDenied("handoff_conflict")
            return result
        if submitted.expected_task_version != task[2]:
            raise KernelDenied("handoff_task_version_changed")
        uow.execute(
            "INSERT INTO panestria.build_handoff(id,plan_id,task_id,attempt_id,lease_epoch,task_version,body,sha256) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb,%s)",
            (
                submitted.handoff_id,
                submitted.plan_id,
                submitted.task_id,
                bundle.attempt_id,
                bundle.lease_epoch,
                task[2],
                result.model_dump_json(),
                result.sha256(),
            ),
        )
        append_event(
            uow,
            goal_id=plan.proposal.goal_id,
            task_id=submitted.task_id,
            actor=actor.owner_id,
            kind="build.plan.handoff",
            payload={
                "handoff_id": submitted.handoff_id,
                "plan_id": submitted.plan_id,
                "sha256": result.sha256(),
                "task_completion_authority": "NONE",
            },
        )
        return result

    def read_handoff(
        self, uow: UnitOfWork, actor: Actor, identifier: str, evidence: BuildEvidenceService
    ) -> RetainedHandoff:
        row = uow.execute(
            "SELECT h.body,h.sha256 FROM panestria.build_handoff h JOIN panestria.build_plan p "
            "ON p.id=h.plan_id WHERE h.id=%s AND p.owner_id=%s AND p.project_id=%s",
            (identifier, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        record = RetainedHandoff.model_validate_json(json.dumps(row[0]))
        if record.sha256() != str(row[1]).strip():
            raise KernelDenied("handoff_record_unconfirmed")
        # Same reconstruction validates current source/candidate/task membership;
        # prior receipt prevents a second record/event or inference/tool effect.
        return self.handoff(uow, actor, record.submission, evidence)
