"""Reuse canonical PUBLIC zero-cash plan staging and verified plan inspection."""

import json
from uuid import UUID

from panestria.contracts.build_intake import BuildPlanStagingView, BuildPlanSubmission
from panestria.contracts.goal import load_contract
from panestria.contracts.plan import PlanProposal, ProjectInventory
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.plan_store import PlanStore
from panestria.kernel.plan_submission import PlanSubmissionService
from panestria.kernel.uow import UnitOfWork


class BuildIntakeService:
    def stage(self, uow: UnitOfWork, actor: Actor, body: BuildPlanSubmission) -> str:
        proposal = PlanProposal.model_validate_json(json.dumps(body.proposal))
        inventory = ProjectInventory.model_validate_json(json.dumps(body.inventory))
        receipt = PlanSubmissionService().stage(
            uow, actor, body.contract_document, proposal, inventory, "mission-build:" + proposal.plan_id
        )
        return receipt.plan_id

    def inspect(self, uow: UnitOfWork, actor: Actor, identifier: str) -> BuildPlanStagingView:
        if str(UUID(identifier, version=4)) != identifier:
            raise KernelDenied("not_found")
        plan = PlanStore().get(uow, actor, identifier)
        row = uow.execute(
            "SELECT g.status,c.body FROM panestria.goal g JOIN panestria.goal_contract c ON c.goal_id=g.id"
            " WHERE g.id=%s AND g.owner_id=%s AND g.project_id=%s ORDER BY c.version DESC LIMIT 1",
            (plan.proposal.goal_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        contract = load_contract(row[1])  # PlanStore already verified its bound hash and policy.
        if contract.privacy_class != "PUBLIC":
            raise KernelDenied("not_found")
        view = BuildPlanStagingView(
            owner_id=actor.owner_id,
            project_id=actor.project_id,
            goal_id=plan.proposal.goal_id,
            goal_status=row[0],
            contract_document=contract.model_dump(mode="json"),
            plan=plan,
        )
        if len(view.model_dump_json().encode()) > 128 * 1024:
            raise KernelDenied("build_intake_view_limit")
        return view
