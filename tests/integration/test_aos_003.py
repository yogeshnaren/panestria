"""AOS-003-TC01. Atomic DBOS enqueue on disposable PostgreSQL."""

from __future__ import annotations

import hashlib
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import psycopg
import pytest
import sqlalchemy as sa

from panestria.execution.admission import AdmissionReceipt, DurableAdmission, SqlUnitOfWork
from panestria.execution.dbos_runtime import QUEUE_NAME, open_client, probe_launch
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ["docker", "compose", "-f", str(ROOT / "compose.yaml"), "-p", "panestria-s3"]
DATABASE_URL = (
    "postgresql://panestria_synthetic:placeholder-not-a-secret@127.0.0.1:55432/panestria_synthetic"
)
OWNER = "00000000-0000-4000-8000-000000000002"
OTHER = "00000000-0000-4000-8000-000000000099"
PROJECT = "00000000-0000-4000-8000-000000000003"
GOAL = "00000000-0000-4000-8000-000000000001"
TASK = "00000000-0000-4000-8000-0000000000a1"
TASK_B = "00000000-0000-4000-8000-0000000000b2"
ATTEMPT = "00000000-0000-4000-8000-0000000000c1"
ATTEMPT_B = "00000000-0000-4000-8000-0000000000c2"
CONTRACT = "00000000-0000-4000-8000-000000000040"
DIGEST = "ab" * 32
WORKFLOW = "00000000-0000-4000-8000-0000000000d1"
WORKFLOW_B = "00000000-0000-4000-8000-0000000000d2"


def _run(argv: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=ROOT, env=env, text=True, capture_output=True, check=False)


@pytest.fixture(autouse=True)
def _case_metadata(record_property: pytest.RecordProperty) -> None:
    commit = _run(["git", "rev-parse", "HEAD"]).stdout.strip()
    dirty = bool(_run(["git", "status", "--porcelain"]).stdout.strip())
    record_property("gate_case_id", "AOS-003-TC01")
    record_property("candidate_commit", commit)
    record_property("fixture_digest", hashlib.sha256(DIGEST.encode()).hexdigest())
    record_property("lane", "integration")
    record_property("execution_mode", "OS_BOUNDARY")
    record_property("worktree_state", "dirty" if dirty else "clean")


@pytest.fixture(scope="module")
def database_url() -> str:
    env = os.environ.copy()
    env["PANESTRIA_DATABASE_URL"] = DATABASE_URL
    _run([*COMPOSE, "down", "-v"])
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
    upgraded = _run(
        ["uv", "run", "--frozen", "alembic", "-c", "migrations/alembic.ini", "upgrade", "head"],
        env=env,
    )
    assert upgraded.returncode == 0, upgraded.stderr
    try:
        yield DATABASE_URL
    finally:
        _run([*COMPOSE, "down", "-v"])


def _seed(connection: sa.Connection) -> None:
    connection.execute(
        sa.text("INSERT INTO panestria.principal (id, display_name) VALUES (:owner, 'owner'), (:other, 'other')"),
        {"owner": OWNER, "other": OTHER},
    )
    connection.execute(
        sa.text("INSERT INTO panestria.project (id, owner_id) VALUES (:project, :owner)"),
        {"project": PROJECT, "owner": OWNER},
    )
    connection.execute(
        sa.text(
            "INSERT INTO panestria.goal (id, owner_id, project_id, intent, status)"
            " VALUES (:goal, :owner, :project, 'synthetic', 'CREATED')"
        ),
        {"goal": GOAL, "owner": OWNER, "project": PROJECT},
    )
    connection.execute(
        sa.text(
            "INSERT INTO panestria.goal_contract (id, goal_id, version, body, sha256)"
            " VALUES (:contract, :goal, 1, '{}'::jsonb, :digest)"
        ),
        {"contract": CONTRACT, "goal": GOAL, "digest": DIGEST},
    )
    connection.execute(
        sa.text(
            "INSERT INTO panestria.task (id, goal_id, contract_id, name, state) VALUES"
            " (:task, :goal, :contract, 'left', 'CREATED'),"
            " (:task_b, :goal, :contract, 'right', 'CREATED')"
        ),
        {"task": TASK, "task_b": TASK_B, "goal": GOAL, "contract": CONTRACT},
    )
    connection.execute(
        sa.text(
            "INSERT INTO panestria.task_attempt (id, task_id, attempt_number, lease_epoch, status, adapter)"
            " VALUES (:attempt, :task, 1, 0, 'PENDING', 'synthetic'),"
            " (:attempt_b, :task_b, 1, 0, 'PENDING', 'synthetic')"
        ),
        {"attempt": ATTEMPT, "task": TASK, "attempt_b": ATTEMPT_B, "task_b": TASK_B},
    )
    connection.commit()


def _count(connection: sa.Connection, sql: str, params: dict[str, Any] | None = None) -> int:
    value = connection.execute(sa.text(sql), params or {}).scalar_one()
    return int(value)


def test_atomic_enqueue_and_duplicate(database_url: str) -> None:
    isolation = probe_launch(database_url)
    assert isolation == "read committed"
    engine, client = open_client(database_url)
    try:
        admission = DurableAdmission(client)
        actor = Actor(OWNER, PROJECT)
        with engine.connect() as connection:
            _seed(connection)
            queued = _count(
                connection,
                "SELECT count(*) FROM dbos.queues WHERE name = :name",
                {"name": QUEUE_NAME},
            )
        assert queued == 1

        held = engine.connect()
        try:
            held.begin()
            admission.submit(
                SqlUnitOfWork(held),
                actor,
                TASK,
                WORKFLOW,
                attempt_id=ATTEMPT,
                idempotency_key="admit-1",
                contract_sha256=DIGEST,
            )
            with engine.connect() as other:
                assert _count(other, "SELECT count(*) FROM dbos.workflow_status") == 0
                assert _count(other, "SELECT count(*) FROM panestria.workflow_link") == 0
                assert _count(other, "SELECT count(*) FROM panestria.task_event") == 0
        finally:
            held.rollback()
            held.close()
        with engine.connect() as connection:
            assert _count(connection, "SELECT count(*) FROM dbos.workflow_status") == 0
            assert _count(connection, "SELECT count(*) FROM panestria.workflow_link") == 0

        with engine.connect() as connection:
            with pytest.raises(KernelDenied) as hidden:
                admission.submit(
                    SqlUnitOfWork(connection),
                    Actor(OTHER, PROJECT),
                    TASK,
                    WORKFLOW,
                    attempt_id=ATTEMPT,
                    idempotency_key="foreign",
                    contract_sha256=DIGEST,
                )
            assert hidden.value.code == "not_found"
            connection.rollback()
        with engine.connect() as connection:
            assert _count(connection, "SELECT count(*) FROM dbos.workflow_status") == 0

        with engine.connect() as connection:
            receipt = admission.submit(
                SqlUnitOfWork(connection),
                actor,
                TASK,
                WORKFLOW,
                attempt_id=ATTEMPT,
                idempotency_key="admit-1",
                contract_sha256=DIGEST,
            )
            connection.commit()
        assert receipt.replayed is False
        assert receipt.workflow_id == WORKFLOW
        with engine.connect() as connection:
            assert _count(
                connection,
                "SELECT count(*) FROM dbos.workflow_status WHERE workflow_uuid = :workflow",
                {"workflow": WORKFLOW},
            ) == 1
            assert _count(connection, "SELECT count(*) FROM panestria.workflow_link") == 1
            assert _count(
                connection,
                "SELECT count(*) FROM panestria.task_event WHERE kind = 'task.admitted'",
            ) == 1

        with engine.connect() as connection:
            replay = admission.submit(
                SqlUnitOfWork(connection),
                actor,
                TASK,
                WORKFLOW,
                attempt_id=ATTEMPT,
                idempotency_key="admit-1",
                contract_sha256=DIGEST,
            )
            connection.commit()
        assert replay.replayed is True
        assert replay.workflow_id == WORKFLOW
        with engine.connect() as connection:
            assert _count(connection, "SELECT count(*) FROM dbos.workflow_status") == 1
            with pytest.raises(KernelDenied) as conflict:
                admission.submit(
                    SqlUnitOfWork(connection),
                    actor,
                    TASK,
                    WORKFLOW,
                    attempt_id=ATTEMPT,
                    idempotency_key="admit-1",
                    contract_sha256="cd" * 32,
                )
            assert conflict.value.code == "idempotency_conflict"
            connection.rollback()
        with engine.connect() as connection:
            assert _count(connection, "SELECT count(*) FROM dbos.workflow_status") == 1

        outcomes: list[AdmissionReceipt] = []
        barrier = threading.Barrier(2)

        def _admit() -> None:
            connection = engine.connect()
            try:
                barrier.wait(5)
                receipt = admission.submit(
                    SqlUnitOfWork(connection),
                    actor,
                    TASK_B,
                    WORKFLOW_B,
                    attempt_id=ATTEMPT_B,
                    idempotency_key="admit-race",
                    contract_sha256=DIGEST,
                )
                connection.commit()
                outcomes.append(receipt)
            finally:
                connection.close()

        threads = [threading.Thread(target=_admit) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        assert sorted(item.replayed for item in outcomes) == [False, True]
        assert {item.workflow_id for item in outcomes} == {WORKFLOW_B}
        with engine.connect() as connection:
            assert _count(
                connection,
                "SELECT count(*) FROM dbos.workflow_status WHERE workflow_uuid = :workflow",
                {"workflow": WORKFLOW_B},
            ) == 1
            assert _count(
                connection,
                "SELECT count(*) FROM panestria.workflow_link WHERE task_id = :task",
                {"task": TASK_B},
            ) == 1
    finally:
        client.destroy()
        engine.dispose()
