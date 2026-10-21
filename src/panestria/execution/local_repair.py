"""One explicitly requested local repair draft from canonical stopped work.

This is a proposal prefilter, not PlanRevisionService consent or admission. No
transaction spans generation. Publication rechecks the full observed basis;
unknown physical work and repeated unchanged failures stop before inference.
"""

from pathlib import Path

from panestria.config_plan import PlanModelSettings
from panestria.contracts.build import canonical_sha256
from panestria.contracts.goal import GoalContract
from panestria.contracts.plan import PlanRevisionConsent, StoredPlan
from panestria.contracts.plan_draft import RepairDraftContext
from panestria.execution.local_plan import LocalBuildPlanner, PlanGenerator
from panestria.execution.owner_build import OwnerBuild
from panestria.kernel.build import BuildEvidenceService
from panestria.kernel.build_progress import BuildProgressService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.plan_store import PlanStore
from panestria.kernel.uow import UnitOfWork


class LocalBuildRepair:
    def __init__(self, owner: OwnerBuild, settings: PlanModelSettings, model: PlanGenerator | None = None):
        if (str(settings.owner_id), str(settings.project_id)) != (owner.actor.owner_id, owner.actor.project_id):
            raise KernelDenied("local_repair_scope_mismatch")
        self.owner = owner
        self.planner = LocalBuildPlanner(settings, model)

    def _basis(
        self, plan_id: str, parent_sha256: str, proof_sha256: str, maximum_versions: int
    ) -> tuple[StoredPlan, GoalContract, RepairDraftContext]:
        if type(maximum_versions) is not int or not 2 <= maximum_versions <= 3:
            raise KernelDenied("plan_repair_limit_invalid")
        owner = self.owner
        with owner.connect() as c:
            c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            uow, store = UnitOfWork(c), PlanStore()
            parent = store.get(uow, owner.actor, plan_id)
            _, _, contract = store._goal(uow, owner.actor, parent.proposal.goal_id, read_only=True)
            progress = BuildProgressService().inspect(
                uow, owner.actor, parent.proposal.goal_id, BuildEvidenceService(owner.reports)
            )
            latest = c.execute(
                "SELECT id::text FROM panestria.build_plan WHERE goal_id=%s ORDER BY version DESC LIMIT 1",
                (parent.proposal.goal_id,),
            ).fetchone()
            if (
                parent.proposal.sha256() != parent_sha256
                or parent.state != "ACCEPTED"
                or latest != (plan_id,)
                or progress.current_plan_id != plan_id
                or progress.goal_status not in {"CREATED", "ACTIVE"}
            ):
                raise KernelDenied("local_repair_parent_not_current_stopped_plan")
            if contract.privacy_class != "PUBLIC" or contract.budget.max_api_usd != "0":
                raise KernelDenied("local_repair_public_zero_cash_required")
            if isinstance(parent.consent, PlanRevisionConsent) and parent.consent.maximum_versions != maximum_versions:
                raise KernelDenied("plan_repair_limit_change_requires_authorization")
            if progress.repair.versions_used >= maximum_versions:
                raise KernelDenied("plan_repair_limit_exhausted")
            if progress.repair.wall_envelope_remaining_seconds < 2:
                raise KernelDenied("plan_repair_budget_exhausted")
            if progress.repair.repeated_failure_count >= 2:
                raise KernelDenied("local_repair_repeated_failure_owner_review_required")
            if progress.repair.held_claims or progress.repair.unconfirmed_invocations:
                raise KernelDenied("plan_previous_work_unconfirmed")
            tasks = c.execute(
                "SELECT state FROM panestria.task WHERE goal_id=%s", (parent.proposal.goal_id,)
            ).fetchall()
            safe = {"CREATED", "READY", "RETRY_WAIT", "COMPLETED", "FAILED", "CANCELLED", "REJECTED"}
            if (
                any(r[0] not in safe for r in tasks)
                or c.execute(
                    "SELECT 1 FROM panestria.side_effect s JOIN panestria.task t ON t.id=s.task_id "
                    "WHERE t.goal_id=%s AND s.state!='PREPARED' LIMIT 1",
                    (parent.proposal.goal_id,),
                ).fetchone()
            ):
                raise KernelDenied("plan_previous_work_unconfirmed")
            current = next(p for p in progress.plans if p.plan_id == plan_id)
            if any(m.evidence_status == "UNCONFIRMED" for m in current.milestones):
                raise KernelDenied("local_repair_evidence_unconfirmed")
            failures = tuple(
                (m.task_id, m.state, m.checks, m.failure_fingerprint)
                for m in current.milestones
                if m.state in {"FAILED", "REJECTED", "CANCELLED"}
            )
            if not failures:
                raise KernelDenied("local_repair_stopped_failure_required")
            proof = c.execute(
                "SELECT r.proof,r.proof_sha256,c.plan_id::text FROM panestria.build_claim_release r "
                "JOIN panestria.build_worker_claim c ON c.attempt_id=r.attempt_id "
                "WHERE c.plan_id=%s AND r.reason='VERIFIED_RETURN' AND r.proof_sha256=%s",
                (plan_id, proof_sha256),
            ).fetchone()
            if (
                proof is None
                or canonical_sha256(proof[0]) != str(proof[1]).strip()
                or proof[0].get("plan_id") != plan_id
                or proof[2] != plan_id
            ):
                raise KernelDenied("plan_return_proof_unconfirmed")
            context = RepairDraftContext(
                parent_plan_id=plan_id,
                parent_proposal_sha256=parent_sha256,
                return_proof_sha256=proof_sha256,
                parent_version=parent.version,
                maximum_versions=maximum_versions,
                remaining_wall_seconds=progress.repair.wall_envelope_remaining_seconds,
                as_of_event_seq=progress.as_of_event_seq,
                failure_states=failures,
            )
        return parent, contract, context

    def propose(
        self,
        plan_id: str,
        parent_sha256: str,
        proof_sha256: str,
        directory: Path,
        *,
        maximum_versions: int = 3,
        local_model_run: bool = False,
    ) -> dict[str, object]:
        if local_model_run is not True:
            raise KernelDenied("explicit_local_plan_model_intent_required")
        parent, contract, context = self._basis(plan_id, parent_sha256, proof_sha256, maximum_versions)

        def still_current() -> None:
            now, current_contract, current = self._basis(plan_id, parent_sha256, proof_sha256, maximum_versions)
            if now != parent or current_contract != contract or current != context:
                raise KernelDenied("local_repair_source_changed")

        return self.planner.propose(
            contract,
            parent.inventory,
            directory,
            local_model_run=True,
            repair=context,
            publication_guard=still_current,
        )
