"""Actual PostgreSQL lineage, source rollback and consumed review constraints."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from test_ask_kernel import initialize

from panestria.contracts.memory import MemorySubmission
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork
from panestria.memory.classification import MemoryClassificationService
from panestria.memory.reclassification import ReclassificationService
from panestria.memory.service import MemoryService

ROOT = Path(__file__).resolve().parents[2]


def alembic(dsn: str, action: str, target: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "migrations/alembic.ini", action, target],
        cwd=ROOT,
        env={**os.environ, "PANESTRIA_DATABASE_URL": dsn},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_legacy_upgrade_preserves_originals_and_refuses_audit_loss(r1_database: str) -> None:
    name = "panestria_classification_" + uuid4().hex
    # The fixture supplies a synthetic URI; Alembic intentionally rejects keyword DSNs.
    dsn = r1_database.rsplit("/", 1)[0] + "/" + name
    with psycopg.connect(r1_database, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            assert alembic(dsn, "upgrade", "0017_worker_invocation").returncode == 0
            owner, project = str(uuid4()), str(uuid4())
            ids: list[str] = []
            with psycopg.connect(dsn) as c:
                c.execute("INSERT INTO panestria.principal(id,display_name) VALUES (%s,'legacy fixture')", (owner,))
                c.execute("INSERT INTO panestria.project(id,owner_id) VALUES (%s,%s)", (project, owner))
                for label in ["PUBLIC", "PRIVATE", "RESTRICTED"]:
                    identity = str(uuid4())
                    ids.append(identity)
                    body = "Legacy " + label + " source"
                    c.execute(
                        "INSERT INTO panestria.memory_source"
                        " (id,owner_id,project_id,source_uri,body,sha256,privacy_label,consented_by)"
                        " VALUES (%s,%s,%s,'legacy-fixture',%s,%s,%s,%s)",
                        (identity, owner, project, body, hashlib.sha256(body.encode()).hexdigest(), label, owner),
                    )
                before = c.execute("SELECT * FROM panestria.memory_source ORDER BY id").fetchall()
            upgraded = alembic(dsn, "upgrade", "0018_memory_classification")
            assert upgraded.returncode == 0, upgraded.stderr
            service = MemoryClassificationService()
            with psycopg.connect(dsn) as c:
                assert c.execute("SELECT * FROM panestria.memory_source ORDER BY id").fetchall() == before
                results = [service.get(UnitOfWork(c), Actor(owner, project), identity) for identity in ids]
                assert [r.original_label for r in results] == ["PUBLIC", "PRIVATE", "RESTRICTED"]
                assert [r.effective_label for r in results] == ["PUBLIC", "RESTRICTED", "RESTRICTED"]
                assert results[1].interpretation == "LEGACY_RESTRICTED"
                assert all(
                    r.origin == "MIGRATION" and r.policy_ref is None and r.resolver_version == 1 for r in results
                )
            denied = alembic(dsn, "downgrade", "0017_worker_invocation")
            assert denied.returncode != 0 and "classification audit exists" in denied.stderr
            with psycopg.connect(dsn) as c:
                assert c.execute("SELECT count(*) FROM panestria.memory_classification").fetchone() == (3,)
                assert c.execute("SELECT version_num FROM alembic_version").fetchone() == (
                    "0018_memory_classification",
                )
                assert c.execute("SELECT * FROM panestria.memory_source ORDER BY id").fetchall() == before
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def test_source_and_classification_commit_or_rollback_together(r1_task: dict[str, str], tmp_path: Path) -> None:
    actor, _ = initialize(r1_task, tmp_path)
    service, memory = MemoryClassificationService(), MemoryService()
    with psycopg.connect(r1_task["dsn"]) as c:
        uow = UnitOfWork(c)
        source = memory.add(uow, actor, MemorySubmission(body="Private synthetic preference", label="PRIVATE"))
        record = service.get(uow, actor, source.source_id)
        assert record.original_label == "PRIVATE" and record.effective_label == "RESTRICTED"
        assert record.origin == "SOURCE_WRITE" and record.policy_ref is not None and record.review_id is None
        assert record.source_sha256 == source.sha256 and record.consented_by == actor.owner_id
        c.rollback()
        with pytest.raises(KernelDenied, match="not_found"), c.transaction():
            service.get(uow, actor, source.source_id)
        assert c.execute("SELECT id FROM panestria.memory_source WHERE id=%s", (source.source_id,)).fetchone() is None
        kept = memory.add(uow, actor, MemorySubmission(body="Public synthetic preference", label="PUBLIC"))
        c.commit()
        assert service.get(uow, actor, kept.source_id).effective_label == "PUBLIC"
    with psycopg.connect(r1_task["dsn"]) as fresh:
        assert service.get(UnitOfWork(fresh), actor, kept.source_id).source_sha256 == kept.sha256


def test_scoped_reads_and_immutable_classification(r1_task: dict[str, str], tmp_path: Path) -> None:
    actor, _ = initialize(r1_task, tmp_path)
    service = MemoryClassificationService()
    with psycopg.connect(r1_task["dsn"]) as c:
        uow = UnitOfWork(c)
        ref = MemoryService().add(uow, actor, MemorySubmission(body="Original private source", label="PRIVATE"))
        c.commit()
        original = service.get(uow, actor, ref.source_id)
        c.commit()
        for other in [Actor(str(uuid4()), actor.project_id), Actor(actor.owner_id, str(uuid4()))]:
            with pytest.raises(KernelDenied, match="not_found"), c.transaction():
                service.get(uow, other, ref.source_id)
        for command in [
            "UPDATE panestria.memory_classification SET effective_label='PUBLIC' WHERE source_id=%s",
            "DELETE FROM panestria.memory_classification WHERE source_id=%s",
        ]:
            with pytest.raises(psycopg.Error, match="immutable"), c.transaction():
                c.execute(command, (ref.source_id,))
        assert service.get(uow, actor, ref.source_id) == original
        c.commit()
        with pytest.raises(psycopg.errors.ForeignKeyViolation), c.transaction():
            c.execute(
                "INSERT INTO panestria.memory_classification"
                " (source_id,owner_id,project_id,source_sha256,original_label,effective_label,interpretation,"
                " resolver_version,origin,consented_by)"
                " VALUES (%s,%s,%s,%s,'PUBLIC','PUBLIC','CANONICAL',1,'SOURCE_WRITE',%s)",
                (str(uuid4()), actor.owner_id, actor.project_id, "ab" * 32, actor.owner_id),
            )


def test_only_consumed_exact_owner_review_can_classify_new_source(r1_task: dict[str, str], tmp_path: Path) -> None:
    actor, _ = initialize(r1_task, tmp_path)
    memory, service, reviews = MemoryService(), MemoryClassificationService(), ReclassificationService()
    with psycopg.connect(r1_task["dsn"]) as c:
        uow = UnitOfWork(c)
        first = memory.add(uow, actor, MemorySubmission(body="Legacy private preference", label="PRIVATE"))
        proposed = MemorySubmission(body="Approved public summary", label="PUBLIC")
        review = reviews.propose(uow, actor, first.item_id, 0, proposed)
        c.commit()
        with pytest.raises(psycopg.Error, match="classification_review_invalid"), c.transaction():
            memory._source(uow, actor, proposed, str(review["review_id"]))
        reviews.decide(uow, actor, str(review["review_id"]), str(review["effect_digest"]), "approve")
        current = memory.correct(uow, actor, first.item_id, 0, proposed, review_id=str(review["review_id"]))
        c.commit()
        old, new = service.get(uow, actor, first.source_id), service.get(uow, actor, current.source_id)
        assert old.original_label == "PRIVATE" and old.effective_label == "RESTRICTED" and old.review_id is None
        assert new.original_label == new.effective_label == "PUBLIC" and new.review_id == review["review_id"]
        assert new.review_effect_digest == review["effect_digest"] and new.review_decided_by == actor.owner_id
        assert new.policy_ref == old.policy_ref
        c.commit()
        with pytest.raises(psycopg.errors.UniqueViolation), c.transaction():
            memory._source(uow, actor, proposed, str(review["review_id"]))
