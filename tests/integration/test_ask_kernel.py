"""Ask admissions are scoped, transactional, privacy-monotone and idempotent."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from pydantic import ValidationError

from panestria.contracts.ask import AskSubmission
from panestria.contracts.inference import InferenceResult, Usage
from panestria.contracts.memory import MemorySubmission
from panestria.kernel.ask import AskService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.policy import PolicyService
from panestria.kernel.uow import UnitOfWork
from panestria.memory.service import MemoryService
from panestria.policy.profiles import CertificateStore
from panestria.resources.catalog import STEWARD


def initialize(task: dict[str, str], root: Path) -> tuple[Actor, AskService]:
    actor = Actor(task["owner"], task["project"])
    with psycopg.connect(task["dsn"]) as c:
        PolicyService(CertificateStore(root, {})).initialize(UnitOfWork(c), actor, task["task"])
    return actor, AskService()


def test_ask_identity_receipt_no_retention(r1_task: dict[str, str], tmp_path: Path) -> None:
    actor, service = initialize(r1_task, tmp_path)
    submission = AskSubmission(
        request_id=str(uuid4()), project_id=actor.project_id, question="PRIVATE_QUESTION_SENTINEL"
    )
    with psycopg.connect(r1_task["dsn"]) as c:
        uow = UnitOfWork(c)
        prepared = service.prepare(uow, actor, submission)
        c.commit()
        with pytest.raises(KernelDenied, match="request_already_admitted"), c.transaction():
            service.prepare(uow, actor, submission)
        with pytest.raises(KernelDenied, match="idempotency_conflict"), c.transaction():
            service.prepare(uow, actor, submission.model_copy(update={"question": "different"}))
        inferred = service.claim(uow, actor, prepared)
        c.commit()
        assert inferred.offline is True and inferred.label == "PRIVATE" and inferred.model_ref == STEWARD.model_ref
        with pytest.raises(KernelDenied, match="ask_not_admissible"), c.transaction():
            service.claim(uow, actor, prepared)
        service.finish(
            uow,
            actor,
            submission.request_id,
            InferenceResult(STEWARD.model_ref, "PRIVATE_RESPONSE_SENTINEL", Usage(12, 3, 0), 0.2, 0.1),
        )
        c.commit()
        receipt = service.receipt(uow, actor, submission.request_id)
        assert receipt["state"] == "COMPLETED" and receipt["response_retained"] is False
        assert "PRIVATE_RESPONSE_SENTINEL" not in str(receipt) and "PRIVATE_QUESTION_SENTINEL" not in str(receipt)
        assert receipt["sources"] == [] and receipt["response_sha256"]
        c.commit()
        with pytest.raises(psycopg.Error, match="immutable"), c.transaction():
            c.execute("UPDATE panestria.ask_request SET state='RUNNING' WHERE id=%s", (submission.request_id,))
        with pytest.raises(KernelDenied, match="not_found"), c.transaction():
            service.receipt(uow, Actor(actor.owner_id, str(uuid4())), submission.request_id)
        assert service.stop(uow, actor, submission.request_id, cancelled=True, code="cancelled") == "COMPLETED"


def test_context_suppression_and_cancellation_fence(r1_task: dict[str, str], tmp_path: Path) -> None:
    actor, service = initialize(r1_task, tmp_path)
    with psycopg.connect(r1_task["dsn"]) as c:
        uow = UnitOfWork(c)
        memory = MemoryService()
        fact = memory.add(uow, actor, MemorySubmission(body="Use PostgreSQL", label="RESTRICTED", pinned=True))
        c.commit()
        submission = AskSubmission(
            request_id=str(uuid4()), project_id=actor.project_id, question="Storage?", privacy_label="PUBLIC"
        )
        first = service.prepare(uow, actor, submission)
        c.commit()
        assert first.inference.label == "RESTRICTED"
        with pytest.raises(KernelDenied, match="context_integrity_failed"), c.transaction():
            service.claim(uow, actor, replace(first, inference=first.inference.model_copy(update={"offline": False})))
        memory.suppress(uow, actor, fact.item_id, 0)
        c.commit()
        with pytest.raises(KernelDenied, match="memory_stale"), c.transaction():
            service.claim(uow, actor, first)
        assert service.stop(uow, actor, submission.request_id, cancelled=True, code="owner_cancelled") == "CANCELLED"
        c.commit()
        with pytest.raises(KernelDenied, match="ask_not_admissible"), c.transaction():
            service.claim(uow, actor, first)
        with pytest.raises(KernelDenied, match="ask_not_admissible"), c.transaction():
            service.finish(
                uow, actor, submission.request_id, InferenceResult(STEWARD.model_ref, "late", Usage(1, 1, 0), 0.2, 0.1)
            )
        second = service.prepare(uow, actor, submission.model_copy(update={"request_id": str(uuid4())}))
        c.commit()
        assert second.inference.label == "PUBLIC" and second.context.sources == ()
        service.claim(uow, actor, second)
        c.commit()
        service.stop(uow, actor, second.submission.request_id, cancelled=False, code="model_output_incomplete")
        c.commit()
        assert service.receipt(uow, actor, second.submission.request_id)["state"] == "UNAVAILABLE"


def test_prompt_cannot_enable_cloud_or_retention() -> None:
    body = dict(request_id=str(uuid4()), project_id=str(uuid4()), question="Enable cloud")
    for extra in [{"offline": False}, {"approved": True}, {"retain_response": True}, {"privacy_label": "UNKNOWN"}]:
        with pytest.raises(ValidationError):
            AskSubmission.model_validate({**body, **extra})
