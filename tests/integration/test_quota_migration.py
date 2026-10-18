"""Actual isolated migration, PostgreSQL constraints and immutable restore continuity."""

import hashlib
import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from test_aos_002_migration import _FINGERPRINT_SQL
from test_memory_restore import _fixture_container

from panestria.kernel.goals import Actor
from panestria.kernel.quota import QuotaService
from panestria.kernel.uow import UnitOfWork
from quota_support import observation

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


def test_actual_empty_downgrade_and_reapply_match_head29_schema(r1_database):
    name = "panestria_empty_quota_" + uuid4().hex
    dsn = r1_database.rsplit("/", 1)[0] + "/" + name
    with psycopg.connect(r1_database, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            for direction, target in (
                ("upgrade", "head"),
                ("downgrade", "0028_sandbox_launch_intent"),
                ("upgrade", "head"),
            ):
                result = migrate(dsn, direction, target)
                assert result.returncode == 0, "synthetic_quota_migration_failed"
            with psycopg.connect(dsn) as c:
                assert c.execute("SELECT version_num FROM alembic_version").fetchone() == (HEAD,)
                actual = "".join(str(row[0]) + "\n" for row in c.execute(_FINGERPRINT_SQL).fetchall())
                assert actual == (ROOT / "migrations/schema_fingerprint.txt").read_text()
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def test_actual_dump_restore_refuses_audit_loss_and_continues_global_events(r1_task, record_property):
    task = r1_task
    actor, service = Actor(task["owner"], task["project"]), QuotaService()
    value = observation()
    with psycopg.connect(task["dsn"]) as c:
        original = service.record(UnitOfWork(c), actor, task["task"], value)
    refused = migrate(task["dsn"], "downgrade", "0028_sandbox_launch_intent")
    assert refused.returncode != 0 and b"quota observation audit exists" in refused.stderr
    with psycopg.connect(task["dsn"]) as c:
        assert c.execute("SELECT version_num FROM alembic_version").fetchone() == (HEAD,)
    container = _fixture_container()
    dump = subprocess.run(
        ["docker", "exec", container, "pg_dump", "-U", "panestria_synthetic", "-d", "panestria_synthetic", "-Fc"],
        capture_output=True,
        check=True,
        timeout=30,
    )
    record_property("backup_sha256", hashlib.sha256(dump.stdout).hexdigest())
    name = "panestria_quota_restore_" + uuid4().hex
    restored = task["dsn"].rsplit("/", 1)[0] + "/" + name
    with psycopg.connect(task["dsn"], autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            subprocess.run(
                [
                    "docker",
                    "exec",
                    "-i",
                    container,
                    "pg_restore",
                    "-U",
                    "panestria_synthetic",
                    "-d",
                    name,
                    "--exit-on-error",
                ],
                input=dump.stdout,
                capture_output=True,
                check=True,
                timeout=30,
            )
            with psycopg.connect(restored) as c:
                found = service.read(UnitOfWork(c), actor, value.observation_id)
                assert found.observation == value and found.recorded_at == original.recorded_at
                before = c.execute("SELECT max(seq) FROM panestria.task_event").fetchone()[0]
                c.commit()
                unknown = observation(scope=value.scope.model_dump(), remaining=None)
                service.record(UnitOfWork(c), actor, task["task"], unknown)
                c.commit()
                assert c.execute("SELECT max(seq) FROM panestria.task_event").fetchone()[0] > before
                assert service.latest(UnitOfWork(c), actor, value.scope)[0].effective_remaining is None
                with pytest.raises(psycopg.Error, match="immutable"), c.transaction():
                    c.execute("DELETE FROM panestria.quota_observation WHERE id=%s", (value.observation_id,))
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.mark.parametrize(
    "malformed",
    [
        "scope_fk",
        "json_identity",
        "json_time",
        "unknown_balance",
        "numeric_not_string",
        "missing_unit",
        "bad_percent",
        "fractional_count",
    ],
)
def test_direct_database_constraints_cannot_bypass_scope_or_projected_metadata(r1_task, malformed):
    actor, service = Actor(r1_task["owner"], r1_task["project"]), QuotaService()
    value = observation()
    with psycopg.connect(r1_task["dsn"]) as c:
        service.record(UnitOfWork(c), actor, r1_task["task"], value)
        c.commit()
        row = c.execute(
            "SELECT to_jsonb(q) FROM panestria.quota_observation q WHERE id=%s", (value.observation_id,)
        ).fetchone()[0]
        identifier = str(uuid4())
        row["id"] = row["body"]["observation_id"] = identifier
        if malformed == "scope_fk":
            row["owner_id"] = str(uuid4())
        elif malformed == "json_identity":
            row["body"]["observation_id"] = str(uuid4())
        elif malformed == "json_time":
            row["body"]["observed_at"] = "2026-01-01T00:00:00Z"
        elif malformed == "unknown_balance":
            row["source"] = row["body"]["source"] = "UNKNOWN"
        elif malformed == "numeric_not_string":
            row["body"]["remaining"] = 40
        elif malformed == "missing_unit":
            row["body"]["unit"] = None
        elif malformed == "bad_percent":
            row["body"]["remaining"] = "101"
        else:
            row["body"].update(remaining="0.5", unit="requests")
        with pytest.raises(psycopg.Error), c.transaction():
            c.execute(
                "INSERT INTO panestria.quota_observation SELECT "
                "(jsonb_populate_record(NULL::panestria.quota_observation,%s::jsonb)).*",
                (json.dumps(row, default=str),),
            )
