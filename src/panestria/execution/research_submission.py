"""Private CAS question bytes precede the atomic DB staging transaction; no egress."""

from collections.abc import Mapping
from pathlib import Path
from uuid import UUID, uuid5

import psycopg
from pydantic import SecretStr

from panestria.contracts.goal import load_contract
from panestria.contracts.research import ResearchArtifactRef, ResearchLimits, ResearchRequestRecord, ResearchScope
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.research_blobs import ResearchBlobStore
from panestria.kernel.research_submission import ResearchSubmissionReceipt, ResearchSubmissionService
from panestria.kernel.uow import UnitOfWork


def stage_question(
    dsn: str,
    actor: Actor,
    root: Path,
    document: Mapping[str, object],
    question: SecretStr,
    limits: ResearchLimits,
    idempotency_key: str,
    *,
    public_question: bool,
    uow: UnitOfWork | None = None,
) -> ResearchSubmissionReceipt:
    if public_question is not True or type(question) is not SecretStr:
        raise KernelDenied("explicit_public_question_required")
    contract = load_contract(dict(document))
    limits = ResearchLimits.model_validate(limits)
    if (contract.owner_id, contract.project_id) != (
        actor.owner_id,
        actor.project_id,
    ) or contract.privacy_class != "PUBLIC":
        raise KernelDenied("public_research_submission_required")
    raw = question.get_secret_value().encode("utf-8")
    if not 0 < len(raw) <= 65536 or not raw.decode().strip():
        raise KernelDenied("research_question_size_or_content")
    goal_id = str(contract.goal_id)
    task_id = str(uuid5(UUID(goal_id), "owner-research-task-v1"))
    request_id = str(uuid5(UUID(goal_id), "owner-research-request-v1"))
    artifact_id = str(uuid5(UUID(goal_id), "owner-research-question-v1"))
    # A filesystem write is not a DB transaction. Put immutable bytes first;
    # a later DB rollback can leave an unreferenced private blob, never a
    # committed request pointing at bytes that were not acknowledged durable.
    with ResearchBlobStore(root, actor) as blobs:
        blob = blobs.put(raw)
    request = ResearchRequestRecord(
        request_id=request_id,
        scope=ResearchScope(owner_id=actor.owner_id, project_id=actor.project_id, goal_id=goal_id, task_id=task_id),
        question=ResearchArtifactRef(
            artifact_id=artifact_id,
            task_id=task_id,
            sha256=blob.sha256,
            size_bytes=blob.size_bytes,
            privacy_label="PUBLIC",
        ),
        limits=limits,
    )
    if uow is not None:
        return ResearchSubmissionService().stage(uow, actor, document, request, idempotency_key)
    with psycopg.connect(dsn, connect_timeout=2, options="-c statement_timeout=5000 -c lock_timeout=1000") as c:
        return ResearchSubmissionService().stage(UnitOfWork(c), actor, document, request, idempotency_key)
