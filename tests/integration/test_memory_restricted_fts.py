"""MVP-X07 / F-AI2: restricted memory plaintext never enters PostgreSQL full-text search."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import psycopg
import pytest

from panestria.contracts.memory import MemorySubmission
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork
from panestria.memory.service import MemoryService

ROOT = Path(__file__).resolve().parents[2]


def _alembic(dsn: str, *action: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "--frozen", "alembic", "-c", "migrations/alembic.ini", *action],
        cwd=ROOT,
        env={**os.environ, "PANESTRIA_DATABASE_URL": dsn},
        capture_output=True,
        text=True,
        timeout=120,
    )


def _documents(c: psycopg.Connection) -> dict[str, bool]:
    rows = c.execute(
        "SELECT r.body,r.search_document IS NOT NULL FROM panestria.memory_revision r ORDER BY r.body"
    ).fetchall()
    return {str(body): bool(indexed) for body, indexed in rows}


def test_f_ai2_upgrade_clears_legacy_restricted_lexemes_and_indexes_only_permitted(r1_migration_task):
    f = r1_migration_task
    actor, service = Actor(f["owner"], f["project"]), MemoryService()
    assert _alembic(f["dsn"], "downgrade", "0040_phone_devices").returncode == 0
    with psycopg.connect(f["dsn"]) as c:
        uow = UnitOfWork(c)
        for label in ("PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED", "PRIVATE"):
            service.add(uow, actor, MemorySubmission(body=f"storage {label.lower()} fact", label=label))
        c.commit()
        assert all(_documents(c).values())  # The N-1 schema indexed every label.
    upgraded = _alembic(f["dsn"], "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr
    expected = {
        "storage public fact": True,
        "storage internal fact": True,
        "storage confidential fact": True,
        "storage restricted fact": False,
        "storage private fact": False,
    }
    with psycopg.connect(f["dsn"]) as c:
        uow = UnitOfWork(c)
        assert _documents(c) == expected
        hits = {hit.body for hit in service.search(uow, actor, "storage")}
        assert hits == {"storage public fact", "storage internal fact", "storage confidential fact"}
        # New rows follow the same rule, and a caller-supplied document is replaced.
        service.add(uow, actor, MemorySubmission(body="storage new restricted fact", label="RESTRICTED"))
        service.add(uow, actor, MemorySubmission(body="storage new public fact", label="PUBLIC"))
        c.commit()
        documents = _documents(c)
        assert documents["storage new restricted fact"] is False and documents["storage new public fact"] is True
        source, item = c.execute(
            "SELECT r.source_id,r.item_id FROM panestria.memory_revision r WHERE r.body='storage new restricted fact'"
        ).fetchone()
        forced = c.execute(
            "INSERT INTO panestria.memory_revision"
            "(id,item_id,owner_id,project_id,version,source_id,body,sha256,search_document)"
            " VALUES (gen_random_uuid(),%s,%s,%s,2,%s,'storage forced',%s,to_tsvector('english','storage'))"
            " RETURNING search_document IS NULL",
            (item, actor.owner_id, actor.project_id, source, "ab" * 32),
        ).fetchone()
        c.rollback()
        assert forced == (True,)
        # Restricted history stays immutable to applications.
        with pytest.raises(psycopg.Error), c.transaction():
            c.execute(
                "UPDATE panestria.memory_revision SET search_document=to_tsvector('english',body)"
                " WHERE body='storage new restricted fact'"
            )
        index = c.execute(
            "SELECT indexdef FROM pg_indexes WHERE schemaname='panestria' AND indexname='ix_memory_fts'"
        ).fetchone()[0]
        assert "WHERE (search_document IS NOT NULL)" in index
    refused = _alembic(f["dsn"], "downgrade", "0040_phone_devices")
    assert refused.returncode != 0 and "downgrade would index its plaintext" in refused.stderr
