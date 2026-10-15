"""Prepare immutable request metadata in the caller transaction, never authorize fetch."""

from dataclasses import dataclass

from psycopg.errors import ForeignKeyViolation
from psycopg.pq import TransactionStatus
from pydantic import ValidationError

from panestria.contracts.build import canonical_sha256
from panestria.contracts.research import ResearchRequestRecord
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.uow import UnitOfWork


@dataclass(frozen=True)
class ResearchRequestReceipt:
    request_id: str
    request_sha256: str
    seq: int
    replayed: bool


class ResearchRequestService:
    def prepare(self, uow: UnitOfWork, actor: Actor, request: ResearchRequestRecord) -> ResearchRequestReceipt:
        if uow.connection.autocommit and uow.connection.info.transaction_status != TransactionStatus.INTRANS:
            raise KernelDenied("research_caller_transaction_required")
        try:
            request = ResearchRequestRecord.model_validate(request)
        except ValidationError:
            raise KernelDenied("invalid_research_request") from None
        scope, question, limits = request.scope, request.question, request.limits
        if (scope.owner_id, scope.project_id) != (actor.owner_id, actor.project_id):
            raise KernelDenied("not_found")
        found = uow.execute(
            "SELECT 1 FROM panestria.task t JOIN panestria.goal g ON g.id=t.goal_id "
            "WHERE t.id=%s AND g.id=%s AND g.owner_id=%s AND g.project_id=%s",
            (scope.task_id, scope.goal_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if found is None:
            raise KernelDenied("not_found")
        digest = canonical_sha256(request.model_dump(mode="json"))
        try:
            row = uow.execute(
                "INSERT INTO panestria.research_request (id,schema_version,owner_id,project_id,goal_id,task_id,"
                "question_artifact_id,question_sha256,question_size_bytes,privacy_class,max_sources,"
                "max_source_bytes,max_total_bytes,max_redirects,deadline_seconds,request_sha256) "
                "VALUES (%s,1,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT(id) DO NOTHING RETURNING seq",
                (
                    request.request_id,
                    scope.owner_id,
                    scope.project_id,
                    scope.goal_id,
                    scope.task_id,
                    question.artifact_id,
                    question.sha256,
                    question.size_bytes,
                    question.privacy_label,
                    limits.max_sources,
                    limits.max_source_bytes,
                    limits.max_total_bytes,
                    limits.max_redirects,
                    limits.deadline_seconds,
                    digest,
                ),
            ).fetchone()
        except ForeignKeyViolation:
            # Caller must roll back; never continue using an aborted transaction.
            raise KernelDenied("research_artifact_or_scope_mismatch") from None
        if row is None:
            old = uow.execute(
                "SELECT request_sha256,seq FROM panestria.research_request WHERE id=%s "
                "AND owner_id=%s AND project_id=%s AND task_id=%s",
                (request.request_id, actor.owner_id, actor.project_id, scope.task_id),
            ).fetchone()
            if old is None:
                raise KernelDenied("not_found")
            if str(old[0]).strip() != digest:
                raise KernelDenied("research_request_conflict")
            return ResearchRequestReceipt(request.request_id, digest, int(old[1]), True)
        append_event(
            uow,
            goal_id=scope.goal_id,
            task_id=scope.task_id,
            kind="research.request.prepared",
            actor=actor.owner_id,
            payload={"request_id": request.request_id, "request_sha256": digest},
        )
        return ResearchRequestReceipt(request.request_id, digest, int(row[0]), False)
