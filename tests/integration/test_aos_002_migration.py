"""AOS-002-TC02. Kernel migration constraints on disposable PostgreSQL."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import psycopg
import pytest

from panestria.kernel.repositories.goals import EVENT_LOOKUP_SQL, GOAL_LOOKUP_SQL
from panestria.kernel.repositories.tasks import TASKS_BY_GOAL_SQL
from stack_support import COMPOSE, DATABASE_URL

ROOT = Path(__file__).resolve().parents[2]


OWNER = "00000000-0000-4000-8000-000000000010"
OTHER = "00000000-0000-4000-8000-000000000011"
PROJECT = "00000000-0000-4000-8000-000000000020"
GOAL = "00000000-0000-4000-8000-000000000030"
OTHER_GOAL = "00000000-0000-4000-8000-000000000031"
CONTRACT = "00000000-0000-4000-8000-000000000040"
OTHER_CONTRACT = "00000000-0000-4000-8000-000000000041"
TASK = "00000000-0000-4000-8000-000000000050"
EVENT = "00000000-0000-4000-8000-000000000080"
_FOOTPRINT_CEILING = 64 * 1024 * 1024
DIGEST = "ab" * 32
FINGERPRINT = ROOT / "migrations" / "schema_fingerprint.txt"
SCHEMA_SNAPSHOT = ROOT / "docs" / "contracts" / "schema-snapshot.txt"
_FINGERPRINT_SQL = """
SELECT 'column ' || table_name || ' ' || column_name || ' ' || udt_name || ' ' || is_nullable
FROM information_schema.columns
WHERE table_schema = 'panestria'
UNION ALL
SELECT 'constraint ' || conrelid::regclass::text || ' ' || contype::text || ' ' || pg_get_constraintdef(oid)
FROM pg_constraint
WHERE connamespace = 'panestria'::regnamespace
UNION ALL
SELECT 'index ' || indexdef
FROM pg_indexes
WHERE schemaname = 'panestria'
ORDER BY 1
"""


def _run(argv: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=ROOT, env=env, text=True, capture_output=True, check=False)


@pytest.fixture(autouse=True)
def _case_metadata(record_property: pytest.RecordProperty) -> None:
    commit = _run(["git", "rev-parse", "HEAD"]).stdout.strip()
    dirty = bool(_run(["git", "status", "--porcelain"]).stdout.strip())
    record_property("gate_case_id", "AOS-002-TC02")
    record_property("candidate_commit", commit)
    record_property("fixture_digest", hashlib.sha256(DIGEST.encode()).hexdigest())
    record_property("lane", "migration")
    record_property("execution_mode", "OS_BOUNDARY")
    record_property("worktree_state", "dirty" if dirty else "clean")


def _alembic(revision: str, env: dict[str, str]) -> None:
    completed = _run(
        ["uv", "run", "--frozen", "alembic", "-c", "migrations/alembic.ini", *revision.split()],
        env=env,
    )
    assert completed.returncode == 0, completed.stderr


def _denied(connection: psycopg.Connection[tuple[object, ...]], sql: str, params: tuple[object, ...]) -> None:
    with pytest.raises(psycopg.Error):
        with connection.transaction():
            connection.execute(sql, params)


def test_kernel_migration_rejects_bad_scope_and_reapplies() -> None:
    env = os.environ.copy()
    env["PANESTRIA_DATABASE_URL"] = DATABASE_URL
    _run([*COMPOSE, "down", "-v"])
    try:
        up = _run([*COMPOSE, "up", "-d", "--wait"], env=env)
        assert up.returncode == 0, up.stderr
        deadline = time.monotonic() + 30
        while True:
            try:
                with psycopg.connect(DATABASE_URL, connect_timeout=2) as connection:
                    connection.execute("SELECT 1")
                break
            except psycopg.Error:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.5)
        _alembic("upgrade head", env)
        with psycopg.connect(DATABASE_URL) as connection:
            _seed(connection)
            _denied(
                connection,
                "INSERT INTO panestria.goal"
                " (id, owner_id, project_id, intent, status)"
                " VALUES (%s, %s, %s, 'foreign', 'CREATED')",
                ("00000000-0000-4000-8000-000000000032", OTHER, PROJECT),
            )
            _denied(
                connection,
                "INSERT INTO panestria.task"
                " (id, goal_id, contract_id, name, state)"
                " VALUES (%s, %s, %s, 'crossed', 'CREATED')",
                ("00000000-0000-4000-8000-000000000051", GOAL, OTHER_CONTRACT),
            )
            _denied(
                connection,
                "INSERT INTO panestria.task_attempt"
                " (id, task_id, attempt_number, lease_epoch, status, adapter)"
                " VALUES (%s, %s, 1, 0, 'PENDING', 'mock')",
                ("00000000-0000-4000-8000-000000000061", "00000000-0000-4000-8000-000000000099"),
            )
            _denied(
                connection,
                "INSERT INTO panestria.task"
                " (id, goal_id, contract_id, name, state)"
                " VALUES (%s, %s, %s, 'bad-state', 'DONE')",
                ("00000000-0000-4000-8000-000000000052", GOAL, CONTRACT),
            )
            _denied(
                connection,
                "UPDATE panestria.goal_contract SET body = %s::jsonb WHERE id = %s",
                ('{"changed":true}', CONTRACT),
            )
            _denied(connection, "DELETE FROM panestria.goal_contract WHERE id = %s", (CONTRACT,))
            connection.execute(
                "INSERT INTO panestria.approval_request ("
                " id, goal_id, task_id, owner_id, project_id, minimum_actor_id, action_kind,"
                " effect_digest, policy_version, state, expires_at, preview)"
                " VALUES (%s, %s, %s, %s, %s, %s, 'merge', %s, 'synthetic-1', 'PENDING',"
                " now() + interval '1 hour', %s::jsonb)",
                (
                    "00000000-0000-4000-8000-000000000070",
                    GOAL,
                    TASK,
                    OWNER,
                    PROJECT,
                    OWNER,
                    DIGEST,
                    '{"action_kind":"merge"}',
                ),
            )
            _denied(
                connection,
                "UPDATE panestria.approval_request SET effect_digest = %s WHERE id = %s",
                ("cd" * 32, "00000000-0000-4000-8000-000000000070"),
            )
            version = connection.execute("SELECT version_num FROM alembic_version").fetchone()
            heads = _run(
                ["uv", "run", "--frozen", "alembic", "-c", "migrations/alembic.ini", "heads"],
                env=env,
            )
            assert version is not None
            assert heads.returncode == 0
            assert version[0] == heads.stdout.strip().split()[0]
            expected = FINGERPRINT.read_text(encoding="utf-8")
            assert SCHEMA_SNAPSHOT.read_text(encoding="utf-8") == expected
            assert _schema_fingerprint(connection) == expected
            with connection.transaction():
                connection.execute("ALTER TABLE panestria.goal ADD COLUMN drift_probe text")
                assert _schema_fingerprint(connection) != expected
                connection.execute("ALTER TABLE panestria.goal DROP COLUMN drift_probe")
            assert _schema_fingerprint(connection) == expected
            _assert_lookup_plans(connection)
        _alembic("downgrade 0001_scaffold", env)
        with psycopg.connect(DATABASE_URL) as connection:
            gone = connection.execute("SELECT to_regclass('panestria.goal')").fetchone()
            schema = connection.execute(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = 'panestria'"
            ).fetchone()
            assert gone == (None,)
            assert schema == (1,)
        _alembic("upgrade head", env)
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute(
                "INSERT INTO panestria.principal (id, display_name) VALUES (%s, 'again')",
                (OWNER,),
            )
            connection.commit()
            found = connection.execute(
                "SELECT display_name FROM panestria.principal WHERE id = %s",
                (OWNER,),
            ).fetchone()
            assert found == ("again",)
            assert _schema_fingerprint(connection) == FINGERPRINT.read_text(encoding="utf-8")
    finally:
        _run([*COMPOSE, "down", "-v"])


def _plan_nodes(value: object) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    if isinstance(value, dict):
        nodes.append(value)
        for child in value.values():
            nodes.extend(_plan_nodes(child))
    elif isinstance(value, list):
        for item in value:
            nodes.extend(_plan_nodes(item))
    return nodes


def _explain(
    connection: psycopg.Connection[tuple[object, ...]],
    sql: str,
    params: tuple[object, ...],
) -> list[dict[str, Any]]:
    with connection.transaction():
        connection.execute("SET LOCAL enable_seqscan = off")
        row = connection.execute(f"EXPLAIN (FORMAT JSON) {sql}", params).fetchone()
    assert row is not None
    raw = row[0]
    parsed = json.loads(raw) if isinstance(raw, str) else raw
    assert isinstance(parsed, list)
    return _plan_nodes(parsed)


def _assert_lookup_plans(connection: psycopg.Connection[tuple[object, ...]]) -> None:
    connection.execute(
        "INSERT INTO panestria.task_event (id, goal_id, task_id, kind, actor, payload)"
        " VALUES (%s, %s, %s, 'goal.created', 'synthetic', '{}'::jsonb)",
        (EVENT, GOAL, TASK),
    )
    connection.execute("ANALYZE panestria.goal, panestria.task, panestria.task_event")
    lookups = (
        (GOAL_LOOKUP_SQL, (GOAL, OWNER, PROJECT), {"goal_pkey", "goal_id_project_id_owner_id_key"}),
        (EVENT_LOOKUP_SQL, (GOAL, 0, 20), {"ix_event_goal_seq"}),
        (TASKS_BY_GOAL_SQL, (GOAL,), {"ix_task_goal"}),
    )
    for sql, params, expected in lookups:
        nodes = _explain(connection, sql, params)
        kinds = {node.get("Node Type") for node in nodes}
        indexes = {node.get("Index Name") for node in nodes}
        assert "Seq Scan" not in kinds
        assert indexes & expected
    footprint = connection.execute(
        "SELECT COALESCE(sum(pg_total_relation_size(class.oid)), 0)::bigint"
        " FROM pg_class AS class"
        " JOIN pg_namespace AS namespace ON namespace.oid = class.relnamespace"
        " WHERE namespace.nspname = 'panestria' AND class.relkind IN ('r', 'i', 'm', 't')"
    ).fetchone()
    database = connection.execute("SELECT pg_database_size(current_database())").fetchone()
    assert footprint is not None and database is not None
    size = int(footprint[0])
    assert 0 < size <= _FOOTPRINT_CEILING
    assert size < int(database[0])


def _schema_fingerprint(connection: psycopg.Connection[tuple[object, ...]]) -> str:
    rows = connection.execute(_FINGERPRINT_SQL).fetchall()
    return "".join(f"{row[0]}\n" for row in rows)


def _seed(connection: psycopg.Connection[tuple[object, ...]]) -> None:
    connection.execute(
        "INSERT INTO panestria.principal (id, display_name) VALUES (%s, 'owner'), (%s, 'other')",
        (OWNER, OTHER),
    )
    connection.execute(
        "INSERT INTO panestria.project (id, owner_id) VALUES (%s, %s)",
        (PROJECT, OWNER),
    )
    connection.execute(
        "INSERT INTO panestria.goal (id, owner_id, project_id, intent, status)"
        " VALUES (%s, %s, %s, 'synthetic', 'CREATED'), (%s, %s, %s, 'other', 'CREATED')",
        (GOAL, OWNER, PROJECT, OTHER_GOAL, OWNER, PROJECT),
    )
    connection.execute(
        "INSERT INTO panestria.goal_contract (id, goal_id, version, body, sha256)"
        " VALUES (%s, %s, 1, %s::jsonb, %s), (%s, %s, 1, %s::jsonb, %s)",
        (CONTRACT, GOAL, "{}", DIGEST, OTHER_CONTRACT, OTHER_GOAL, "{}", DIGEST),
    )
    connection.execute(
        "INSERT INTO panestria.task (id, goal_id, contract_id, name, state)"
        " VALUES (%s, %s, %s, 'work', 'CREATED')",
        (TASK, GOAL, CONTRACT),
    )
    connection.commit()
