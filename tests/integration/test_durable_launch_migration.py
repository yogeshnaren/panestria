"""Actual isolated PostgreSQL downgrade/restore/audit continuity; synthetic data only."""

import os
import subprocess
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from test_aos_002_migration import _FINGERPRINT_SQL
from test_memory_restore import _fixture_container

from durable_launch_support import prepared
from panestria.contracts.sandbox_launch import SandboxLaunchObservation
from panestria.kernel.sandbox_launches import SandboxLaunchService
from panestria.kernel.uow import UnitOfWork

ROOT = Path(__file__).resolve().parents[2]
HEAD = "0031_fetch_admission"


def migrate(dsn, direction, target):
    return subprocess.run(
        [str(ROOT / ".venv/bin/alembic"), "-c", "migrations/alembic.ini", direction, target],
        cwd=ROOT,
        env={**os.environ, "PANESTRIA_DATABASE_URL": dsn},
        capture_output=True,
        timeout=30,
    )


def test_actual_empty_downgrade_reapply_matches_observed_current_schema(r1_database):
    name = "panestria_empty_launch_" + uuid4().hex
    dsn = r1_database.rsplit("/", 1)[0] + "/" + name
    with psycopg.connect(r1_database, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            for direction, target in [
                ("upgrade", "head"),
                ("downgrade", "0027_connection_reviews"),
                ("upgrade", "head"),
            ]:
                result = migrate(dsn, direction, target)
                assert result.returncode == 0, "synthetic_launch_schema_roundtrip_failed"
                with psycopg.connect(dsn) as c:
                    expected = "0027_connection_reviews" if direction == "downgrade" else HEAD
                    assert c.execute("SELECT version_num FROM alembic_version").fetchone() == (expected,)
            with psycopg.connect(dsn) as c:
                actual = "".join(str(row[0]) + "\n" for row in c.execute(_FINGERPRINT_SQL).fetchall())
                assert actual == (ROOT / "migrations/schema_fingerprint.txt").read_text()
                assert c.execute("SELECT count(*) FROM panestria.worker_invocation_launch").fetchone() == (0,)
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def test_actual_backup_restore_retains_immutable_intent_and_event_counter_after_reconciliation(r1_task):
    actor, binding, identity, intent = prepared(r1_task)
    service = SandboxLaunchService()
    with psycopg.connect(r1_task["dsn"]) as c:
        service.record(UnitOfWork(c), actor, binding, identity, intent)
    with psycopg.connect(r1_task["dsn"]) as c:
        quota_history = c.execute("SELECT EXISTS(SELECT 1 FROM panestria.quota_observation)").fetchone()[0]
    refused = migrate(r1_task["dsn"], "downgrade", "0027_connection_reviews")
    expected_guard = b"quota observation audit exists" if quota_history else b"sandbox launch audit exists"
    assert refused.returncode != 0 and expected_guard in refused.stderr
    with psycopg.connect(r1_task["dsn"]) as c:
        assert c.execute("SELECT version_num FROM alembic_version").fetchone() == (HEAD,)
        assert service.read(UnitOfWork(c), actor, binding, identity) == intent
    container = _fixture_container()
    dump = subprocess.run(
        ["docker", "exec", container, "pg_dump", "-U", "panestria_synthetic", "-d", "panestria_synthetic", "-Fc"],
        capture_output=True,
        check=True,
        timeout=30,
    )
    name = "panestria_launch_restore_" + uuid4().hex
    restored = r1_task["dsn"].rsplit("/", 1)[0] + "/" + name
    with psycopg.connect(r1_task["dsn"], autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            result = subprocess.run(
                ["docker", "exec", "-i", container, "pg_restore", "-U", "panestria_synthetic", "-d", name],
                input=dump.stdout,
                capture_output=True,
                timeout=30,
            )
            assert result.returncode == 0, "synthetic_launch_restore_failed"
            with psycopg.connect(restored) as c:
                assert service.read(UnitOfWork(c), actor, binding, identity) == intent
                maximum = c.execute("SELECT max(seq) FROM panestria.task_event").fetchone()[0]
                c.commit()
                service.observe(
                    UnitOfWork(c),
                    actor,
                    binding,
                    identity,
                    SandboxLaunchObservation(
                        intent_sha256=intent.sha256(), status="NOT_OBSERVED", reason="no_owned_container_observed"
                    ),
                )
                c.commit()
                assert c.execute("SELECT max(seq) FROM panestria.task_event").fetchone()[0] > maximum
                assert c.execute(
                    "SELECT state FROM panestria.worker_invocation WHERE id=%s", (identity,)
                ).fetchone() == ("UNKNOWN",)
                with pytest.raises(psycopg.Error, match="immutable"), c.transaction():
                    c.execute("DELETE FROM panestria.worker_invocation_launch WHERE invocation_id=%s", (identity,))
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
