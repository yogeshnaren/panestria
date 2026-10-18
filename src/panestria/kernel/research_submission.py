"""Atomically stage an owner question; this grants no execution authority."""

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import uuid4

from psycopg.pq import TransactionStatus

from panestria.contracts.goal import load_contract
from panestria.contracts.research import ResearchRequestRecord
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor, GoalService
from panestria.kernel.repositories.policy import lock_project, require_current_policy
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.research_requests import ResearchRequestService
from panestria.kernel.uow import UnitOfWork


@dataclass(frozen=True)
class ResearchSubmissionReceipt:
    goal_id: str
    task_id: str
    request_id: str
    request_sha256: str
    replayed: bool
    status: str = "STAGED_NO_EXECUTION"


class ResearchSubmissionService:
    def stage(
        self,
        uow: UnitOfWork,
        actor: Actor,
        document: Mapping[str, object],
        request: ResearchRequestRecord,
        idempotency_key: str,
    ) -> ResearchSubmissionReceipt:
        if uow.connection.autocommit and uow.connection.info.transaction_status != TransactionStatus.INTRANS:
            raise KernelDenied("research_caller_transaction_required")
        contract = load_contract(dict(document))  # Retain refusal of unadmitted citation/rubric runners.
        request = ResearchRequestRecord.model_validate(request)
        scope, question = request.scope, request.question
        if (
            (scope.owner_id, scope.project_id, scope.goal_id)
            != (actor.owner_id, actor.project_id, str(contract.goal_id))
            or (contract.owner_id, contract.project_id) != (actor.owner_id, actor.project_id)
            or contract.privacy_class != "PUBLIC"
            or question.privacy_label != "PUBLIC"
            or question.task_id != scope.task_id
            or not 0 < question.size_bytes <= 65536
            or not 1 <= len(idempotency_key) <= 128
        ):
            raise KernelDenied("public_research_submission_required")
        if lock_project(uow, actor) == 0:
            raise KernelDenied("policy_unconfigured")
        require_current_policy(uow, actor, contract.autonomy_profile_ref)
        goal = GoalService().submit(uow, actor, document, idempotency_key)
        if not goal.replayed:
            cid = uow.execute(
                "SELECT id FROM panestria.goal_contract WHERE goal_id=%s AND sha256=%s",
                (scope.goal_id, goal.contract_sha256),
            ).fetchone()
            assert cid is not None
            uow.execute(
                "INSERT INTO panestria.task(id,goal_id,contract_id,name,state) "
                "VALUES(%s,%s,%s,'Owner PUBLIC research question','CREATED')",
                (scope.task_id, scope.goal_id, cid[0]),
            )
            uow.execute(
                "INSERT INTO panestria.artifact(id,task_id,kind,store_key,sha256,privacy_class,size_bytes) "
                "VALUES(%s,%s,'research.question',%s,%s,'PUBLIC',%s)",
                (question.artifact_id, scope.task_id, question.sha256, question.sha256, question.size_bytes),
            )
            # Admission is caller-owned and all-or-nothing. No lease, activation,
            # acceptance verdict, policy change or outward effect is created.
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
            append_event(
                uow,
                goal_id=scope.goal_id,
                task_id=scope.task_id,
                actor=actor.owner_id,
                kind="research.question.staged",
                payload={"request_id": request.request_id, "execution": "NONE"},
            )
        else:
            # Replay may inspect the same request, but cannot create a second
            # task/request or repurpose a goal submitted by another workflow.
            old = uow.execute(
                "SELECT r.task_id::text,r.question_artifact_id::text,a.sha256,a.size_bytes,a.privacy_class "
                "FROM panestria.research_request r JOIN panestria.artifact a ON a.id=r.question_artifact_id "
                "WHERE r.id=%s AND r.goal_id=%s AND r.owner_id=%s AND r.project_id=%s",
                (request.request_id, scope.goal_id, actor.owner_id, actor.project_id),
            ).fetchone()
            if old is None or tuple(str(v).strip() for v in old) != (
                scope.task_id,
                question.artifact_id,
                question.sha256,
                str(question.size_bytes),
                "PUBLIC",
            ):
                raise KernelDenied("research_submission_conflict")
        retained = ResearchRequestService().prepare(uow, actor, request)
        return ResearchSubmissionReceipt(
            scope.goal_id, scope.task_id, request.request_id, retained.request_sha256, goal.replayed
        )
