"""Stage a bounded PUBLIC Build goal/check set and canonical proposal atomically.

No lease, worker, provider permission, inference call or accepted task is created.
The caller owns the same-Postgres transaction; replay never launches anything.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import uuid4

from panestria.contracts.goal import load_contract
from panestria.contracts.plan import PlanProposal, ProjectInventory
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor, GoalService
from panestria.kernel.plan_store import PlanStore
from panestria.kernel.plans import PlanValidator
from panestria.kernel.repositories.policy import lock_project, require_current_policy
from panestria.kernel.uow import UnitOfWork


@dataclass(frozen=True)
class PlanSubmission:
    goal_id: str
    plan_id: str
    proposal_sha256: str
    effect_digest: str
    state: str
    replayed: bool
    execution_authority: str = "NONE"


class PlanSubmissionService:
    def stage(
        self,
        uow: UnitOfWork,
        actor: Actor,
        document: Mapping[str, object],
        proposal: PlanProposal,
        inventory: ProjectInventory,
        idempotency_key: str,
    ) -> PlanSubmission:
        store = PlanStore()
        store._transaction(uow)
        contract = load_contract(dict(document))
        proposal = PlanProposal.model_validate(proposal)
        inventory = ProjectInventory.model_validate(inventory)
        if (
            contract.privacy_class != "PUBLIC"
            or contract.budget.max_api_usd != "0"
            or not 1 <= len(idempotency_key) <= 128
        ):
            raise KernelDenied("public_zero_cash_plan_required")
        PlanValidator().validate(actor, proposal, contract, inventory)
        lock_project(uow, actor)
        require_current_policy(uow, actor, contract.autonomy_profile_ref)
        receipt = GoalService().submit(uow, actor, document, idempotency_key)
        cid = uow.execute(
            "SELECT id::text FROM panestria.goal_contract WHERE goal_id=%s AND sha256=%s",
            (receipt.goal_id, receipt.contract_sha256),
        ).fetchone()
        assert cid is not None
        if receipt.replayed:
            old = store.get(uow, actor, proposal.plan_id)
            if old.proposal != proposal or old.inventory != inventory:
                raise KernelDenied("plan_submission_conflict")
        else:
            for check in contract.acceptance:
                uow.execute(
                    "INSERT INTO panestria.acceptance_check"
                    "(id,contract_id,check_key,description,required,verifier_type,verifier_spec) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb)",
                    (
                        str(uuid4()),
                        cid[0],
                        check.id,
                        check.description,
                        check.required,
                        check.verifier.type,
                        check.verifier.model_dump_json(),
                    ),
                )
        rows = uow.execute(
            "SELECT check_key,description,required,verifier_type,verifier_spec "
            "FROM panestria.acceptance_check WHERE contract_id=%s ORDER BY check_key",
            (cid[0],),
        ).fetchall()
        expected = [
            (check.id, check.description, check.required, check.verifier.type, check.verifier.model_dump(mode="json"))
            for check in sorted(contract.acceptance, key=lambda c: c.id)
        ]
        if rows != expected:
            raise KernelDenied("plan_submission_checks_changed")
        retained = store.prepare(uow, actor, proposal, inventory)
        return PlanSubmission(
            receipt.goal_id,
            proposal.plan_id,
            proposal.sha256(),
            retained.effect_digest,
            retained.state,
            receipt.replayed,
        )
