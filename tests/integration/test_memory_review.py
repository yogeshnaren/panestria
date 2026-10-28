"""Privacy downgrades consume an exact scoped owner review and preserve source history."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from test_ask_kernel import initialize

from panestria.contracts.memory import MemorySubmission
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork
from panestria.memory.reclassification import ReclassificationService
from panestria.memory.service import MemoryService


def test_exact_review_consumed_and_old_label_retained(r1_task: dict[str, str], tmp_path: Path) -> None:
    actor, _ = initialize(r1_task, tmp_path)
    memory, reviews = MemoryService(), ReclassificationService()
    proposed = MemorySubmission(body="Release note: uses PostgreSQL", label="PUBLIC", pinned=True)
    with psycopg.connect(r1_task["dsn"]) as c:
        uow = UnitOfWork(c)
        original = memory.add(uow, actor, MemorySubmission(body="Internal note: uses PostgreSQL", label="RESTRICTED"))
        c.commit()
        review = reviews.propose(uow, actor, original.item_id, 0, proposed)
        c.commit()
        with pytest.raises(KernelDenied, match="memory_review_mismatch"), c.transaction():
            memory.correct(uow, actor, original.item_id, 0, proposed, review_id=review["review_id"])
        with pytest.raises(KernelDenied, match="memory_review_mismatch"), c.transaction():
            reviews.decide(uow, actor, review["review_id"], "00" * 32, "approve")
        with pytest.raises(KernelDenied, match="not_found"), c.transaction():
            reviews.decide(
                uow, Actor(str(uuid4()), actor.project_id), review["review_id"], review["effect_digest"], "approve"
            )
        assert reviews.decide(uow, actor, review["review_id"], review["effect_digest"], "approve") == "APPROVED"
        c.commit()
        with pytest.raises(KernelDenied, match="memory_review_mismatch"), c.transaction():
            memory.correct(
                uow,
                actor,
                original.item_id,
                0,
                proposed.model_copy(update={"body": "different"}),
                review_id=review["review_id"],
            )
        with pytest.raises(psycopg.Error, match="immutable"), c.transaction():
            c.execute("UPDATE panestria.memory_review SET proposed='{}' WHERE id=%s", (review["review_id"],))
        current = memory.correct(uow, actor, original.item_id, 0, proposed, review_id=review["review_id"])
        c.commit()
        assert current.revision == 2 and memory.search(uow, actor, "PostgreSQL")[0].label == "PUBLIC"
        labels = c.execute(
            "SELECT privacy_label,review_id::text FROM panestria.memory_source WHERE id=ANY(%s) ORDER BY created_at",
            ([original.source_id, current.source_id],),
        ).fetchall()
        assert labels == [("RESTRICTED", None), ("PUBLIC", review["review_id"])]
        assert c.execute(
            "SELECT state FROM panestria.memory_review WHERE id=%s", (review["review_id"],)
        ).fetchone() == ("CONSUMED",)
        c.commit()
        with pytest.raises(KernelDenied, match="decision_conflict"), c.transaction():
            reviews.decide(uow, actor, review["review_id"], review["effect_digest"], "approve")
        with pytest.raises(KernelDenied, match="version_conflict"), c.transaction():
            memory.correct(uow, actor, original.item_id, 0, proposed, review_id=review["review_id"])


def test_review_does_not_apply_to_another_revision(r1_task: dict[str, str], tmp_path: Path) -> None:
    actor, _ = initialize(r1_task, tmp_path)
    memory, reviews = MemoryService(), ReclassificationService()
    proposed = MemorySubmission(body="Publish safe preference", label="PUBLIC")
    with psycopg.connect(r1_task["dsn"]) as c:
        uow = UnitOfWork(c)
        first = memory.add(uow, actor, MemorySubmission(body="Private preference", label="PRIVATE"))
        other = memory.add(uow, actor, MemorySubmission(body="Other private preference", label="PRIVATE"))
        c.commit()
        review = reviews.propose(uow, actor, first.item_id, 0, proposed)
        reviews.decide(uow, actor, review["review_id"], review["effect_digest"], "approve")
        c.commit()
        with pytest.raises(KernelDenied, match="memory_review_mismatch"), c.transaction():
            memory.correct(uow, actor, other.item_id, 0, proposed, review_id=review["review_id"])
        memory.correct(
            uow, actor, first.item_id, 0, MemorySubmission(body="Corrected private preference", label="PRIVATE")
        )
        c.commit()
        with pytest.raises(KernelDenied, match="memory_review_mismatch"), c.transaction():
            memory.correct(uow, actor, first.item_id, 1, proposed, review_id=review["review_id"])
        # The mismatched review applied nothing; restricted revisions stay unindexed (MVP-X07).
        assert memory.search(uow, actor, "preference") == []
