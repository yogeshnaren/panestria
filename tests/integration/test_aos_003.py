"""AOS-003-TC01. Atomic DBOS enqueue on disposable PostgreSQL."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import pickle
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import psycopg
import pytest
import sqlalchemy as sa

from panestria.execution.admission import AdmissionReceipt, DurableAdmission, SqlUnitOfWork
from panestria.execution.dbos_runtime import QUEUE_NAME, open_client, probe_launch, sqlalchemy_url
from panestria.execution.recovery import RecoveryReport, connect_for_admission, format_recovery_audit, recovery_instance
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


def _properties(record_property: pytest.RecordProperty, case_id: str) -> None:
    commit = _run(["git", "rev-parse", "HEAD"]).stdout.strip()
    dirty = bool(_run(["git", "status", "--porcelain"]).stdout.strip())
    record_property("gate_case_id", case_id)
    record_property("candidate_commit", commit)
    record_property("fixture_digest", hashlib.sha256(DIGEST.encode()).hexdigest())
    record_property("lane", "chaos" if case_id in {"AOS-003-TC02", "AOS-003-TC03"} else "integration")
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


def test_recovery_instance_is_stable_for_the_process(record_property: pytest.RecordProperty) -> None:
    _properties(record_property, "AOS-003-TC02")
    assert recovery_instance() == recovery_instance()
    report = RecoveryReport("wf-audit", "SUCCESS", "", recovery_instance())
    line = format_recovery_audit(report)
    loaded = json.loads(line)
    assert loaded["recovery_instance"] == recovery_instance()
    assert loaded["workflow_id"] == "wf-audit"
    assert loaded["status"] == "SUCCESS"
    assert "postgresql" not in line


def test_atomic_enqueue_and_duplicate(database_url: str, record_property: pytest.RecordProperty) -> None:
    _properties(record_property, "AOS-003-TC01")
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
            queued_inputs = connection.execute(
                sa.text("SELECT inputs FROM dbos.workflow_input WHERE workflow_uuid = :workflow"),
                {"workflow": WORKFLOW},
            ).scalar_one()
        loaded = pickle.loads(base64.b64decode(str(queued_inputs)))
        assert loaded["args"] == (TASK, DIGEST, 1)

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
        running_task = "00000000-0000-4000-8000-0000000000f1"
        running_attempt = "00000000-0000-4000-8000-0000000000f2"
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO panestria.task (id, goal_id, contract_id, name, state)"
                    " VALUES (:task, :goal, :contract, 'running', 'RUNNING')"
                ),
                {"task": running_task, "goal": GOAL, "contract": CONTRACT},
            )
            connection.execute(
                sa.text(
                    "INSERT INTO panestria.task_attempt"
                    " (id, task_id, attempt_number, lease_epoch, status, adapter)"
                    " VALUES (:attempt, :task, 1, 0, 'PENDING', 'synthetic')"
                ),
                {"attempt": running_attempt, "task": running_task},
            )
        with engine.connect() as connection:
            before = _count(connection, "SELECT count(*) FROM dbos.workflow_status")
            with pytest.raises(KernelDenied) as running:
                admission.submit(
                    SqlUnitOfWork(connection),
                    actor,
                    running_task,
                    "wf-running",
                    attempt_id=running_attempt,
                    idempotency_key="running",
                    contract_sha256=DIGEST,
                )
            assert running.value.code == "illegal_transition"
            connection.rollback()
            with pytest.raises(KernelDenied) as mismatched:
                admission.submit(
                    SqlUnitOfWork(connection),
                    actor,
                    TASK,
                    "wf-other-digest",
                    attempt_id=ATTEMPT,
                    idempotency_key="other-digest",
                    contract_sha256="cd" * 32,
                )
            assert mismatched.value.code == "invalid_contract"
            connection.rollback()
            with pytest.raises(KernelDenied) as changed:
                admission.submit(
                    SqlUnitOfWork(connection),
                    actor,
                    TASK,
                    "wf-changed-identity",
                    attempt_id=ATTEMPT,
                    idempotency_key="admit-1",
                    contract_sha256=DIGEST,
                )
            assert changed.value.code == "idempotency_conflict"
            connection.rollback()
            assert _count(connection, "SELECT count(*) FROM dbos.workflow_status") == before
    finally:
        client.destroy()
        engine.dispose()


TASK_BEFORE = "00000000-0000-4000-8000-0000000000e1"
TASK_AFTER = "00000000-0000-4000-8000-0000000000e2"
TASK_DUP = "00000000-0000-4000-8000-0000000000e3"
ATTEMPT_BEFORE = "00000000-0000-4000-8000-0000000000e4"
ATTEMPT_AFTER = "00000000-0000-4000-8000-0000000000e5"
ATTEMPT_DUP = "00000000-0000-4000-8000-0000000000e6"


def _seed_replay_tasks(engine: sa.Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO panestria.principal (id, display_name) VALUES (:owner, 'owner')"
                " ON CONFLICT (id) DO NOTHING"
            ),
            {"owner": OWNER},
        )
        connection.execute(
            sa.text(
                "INSERT INTO panestria.project (id, owner_id) VALUES (:project, :owner)"
                " ON CONFLICT (id) DO NOTHING"
            ),
            {"project": PROJECT, "owner": OWNER},
        )
        connection.execute(
            sa.text(
                "INSERT INTO panestria.goal (id, owner_id, project_id, intent, status)"
                " VALUES (:goal, :owner, :project, 'synthetic', 'CREATED')"
                " ON CONFLICT (id) DO NOTHING"
            ),
            {"goal": GOAL, "owner": OWNER, "project": PROJECT},
        )
        connection.execute(
            sa.text(
                "INSERT INTO panestria.goal_contract (id, goal_id, version, body, sha256)"
                " VALUES (:contract, :goal, 1, '{}'::jsonb, :digest)"
                " ON CONFLICT (id) DO NOTHING"
            ),
            {"contract": CONTRACT, "goal": GOAL, "digest": DIGEST},
        )
        connection.execute(
            sa.text(
                "INSERT INTO panestria.task (id, goal_id, contract_id, name, state) VALUES"
                " (:before, :goal, :contract, 'before', 'CREATED'),"
                " (:after, :goal, :contract, 'after', 'CREATED'),"
                " (:dup, :goal, :contract, 'dup', 'CREATED')"
            ),
            {"before": TASK_BEFORE, "after": TASK_AFTER, "dup": TASK_DUP, "goal": GOAL, "contract": CONTRACT},
        )
        connection.execute(
            sa.text(
                "INSERT INTO panestria.task_attempt"
                " (id, task_id, attempt_number, lease_epoch, status, adapter) VALUES"
                " (:before, :task_before, 1, 0, 'PENDING', 'synthetic'),"
                " (:after, :task_after, 1, 0, 'PENDING', 'synthetic'),"
                " (:dup, :task_dup, 1, 0, 'PENDING', 'synthetic')"
            ),
            {
                "before": ATTEMPT_BEFORE,
                "task_before": TASK_BEFORE,
                "after": ATTEMPT_AFTER,
                "task_after": TASK_AFTER,
                "dup": ATTEMPT_DUP,
                "task_dup": TASK_DUP,
            },
        )


def _spawn(
    database_url: str,
    *,
    mode: str,
    workflow_id: str,
    task_id: str,
    crash_at: str | None,
    ready: Path | None,
) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["PANESTRIA_DATABASE_URL"] = database_url
    env["PANESTRIA_MODE"] = mode
    env["PANESTRIA_WORKFLOW_ID"] = workflow_id
    env["PANESTRIA_TASK_ID"] = task_id
    env["PANESTRIA_CONTRACT_SHA256"] = DIGEST
    env["PANESTRIA_ATTEMPT"] = "1"
    env.pop("PANESTRIA_CRASH_AT", None)
    env.pop("PANESTRIA_READY_FILE", None)
    if crash_at is not None and ready is not None:
        env["PANESTRIA_CRASH_AT"] = crash_at
        env["PANESTRIA_READY_FILE"] = str(ready)
    return subprocess.Popen(
        ["uv", "run", "--frozen", "python", "-m", "panestria.execution.task_workflow"],
        cwd=ROOT,
        env=env,
        start_new_session=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _wait_ready(path: Path, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if path.exists():
            return
        if process.poll() is not None:
            _stderr = process.stderr.read() if process.stderr is not None else ""
            raise AssertionError(_stderr)
        time.sleep(0.1)
    raise AssertionError("crash gate was not reached")


def _kill(process: subprocess.Popen[str]) -> None:
    os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=5)


def _finish(process: subprocess.Popen[str]) -> None:
    stdout, stderr = process.communicate(timeout=30)
    if process.returncode != 0:
        raise AssertionError(stderr or stdout)


def _task_state(engine: sa.Engine, task_id: str) -> tuple[str, int, int]:
    with engine.connect() as connection:
        row = connection.execute(
            sa.text("SELECT state, row_version FROM panestria.task WHERE id = :task"),
            {"task": task_id},
        ).one()
        events = connection.execute(
            sa.text(
                "SELECT count(*) FROM panestria.task_event"
                " WHERE task_id = :task AND kind = 'task.transition'"
            ),
            {"task": task_id},
        ).scalar_one()
    return str(row[0]), int(row[1]), int(events)


def test_before_after_commit(
    database_url: str,
    record_property: pytest.RecordProperty,
    tmp_path: Path,
) -> None:
    _properties(record_property, "AOS-003-TC02")
    record_property("lane", "chaos")
    engine = sa.create_engine(sqlalchemy_url(database_url))
    try:
        _seed_replay_tasks(engine)
        before_ready = tmp_path / "before"
        before = _spawn(
            database_url,
            mode="run",
            workflow_id="wf-before-commit",
            task_id=TASK_BEFORE,
            crash_at="before-commit",
            ready=before_ready,
        )
        _wait_ready(before_ready, before)
        assert _task_state(engine, TASK_BEFORE) == ("CREATED", 0, 0)
        _kill(before)
        assert _task_state(engine, TASK_BEFORE) == ("CREATED", 0, 0)
        recovered = _spawn(
            database_url,
            mode="recover",
            workflow_id="wf-before-commit",
            task_id=TASK_BEFORE,
            crash_at=None,
            ready=None,
        )
        _finish(recovered)
        assert _task_state(engine, TASK_BEFORE) == ("VALIDATING", 1, 1)

        after_ready = tmp_path / "after"
        after = _spawn(
            database_url,
            mode="run",
            workflow_id="wf-after-commit",
            task_id=TASK_AFTER,
            crash_at="after-commit",
            ready=after_ready,
        )
        _wait_ready(after_ready, after)
        assert _task_state(engine, TASK_AFTER) == ("VALIDATING", 1, 1)
        _kill(after)
        assert _task_state(engine, TASK_AFTER) == ("VALIDATING", 1, 1)
        recovered_after = _spawn(
            database_url,
            mode="recover",
            workflow_id="wf-after-commit",
            task_id=TASK_AFTER,
            crash_at=None,
            ready=None,
        )
        _finish(recovered_after)
        assert _task_state(engine, TASK_AFTER) == ("VALIDATING", 1, 1)

        duplicate = _spawn(
            database_url,
            mode="duplicate",
            workflow_id="wf-duplicate",
            task_id=TASK_DUP,
            crash_at=None,
            ready=None,
        )
        _finish(duplicate)
        assert _task_state(engine, TASK_DUP) == ("VALIDATING", 1, 1)
    finally:
        engine.dispose()


TASK_EFFECT = "00000000-0000-4000-8000-0000000000e7"
TASK_FAIL = "00000000-0000-4000-8000-0000000000e9"
TASK_RESTORE = "00000000-0000-4000-8000-0000000000eb"
ATTEMPT_EFFECT = "00000000-0000-4000-8000-0000000000e8"
ATTEMPT_FAIL = "00000000-0000-4000-8000-0000000000ea"
ATTEMPT_RESTORE = "00000000-0000-4000-8000-0000000000ec"


def _seed_task(engine: sa.Engine, task_id: str, attempt_id: str, name: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO panestria.principal (id, display_name) VALUES (:owner, 'owner')"
                " ON CONFLICT (id) DO NOTHING"
            ),
            {"owner": OWNER},
        )
        connection.execute(
            sa.text(
                "INSERT INTO panestria.project (id, owner_id) VALUES (:project, :owner)"
                " ON CONFLICT (id) DO NOTHING"
            ),
            {"project": PROJECT, "owner": OWNER},
        )
        connection.execute(
            sa.text(
                "INSERT INTO panestria.goal (id, owner_id, project_id, intent, status)"
                " VALUES (:goal, :owner, :project, 'synthetic', 'CREATED')"
                " ON CONFLICT (id) DO NOTHING"
            ),
            {"goal": GOAL, "owner": OWNER, "project": PROJECT},
        )
        connection.execute(
            sa.text(
                "INSERT INTO panestria.goal_contract (id, goal_id, version, body, sha256)"
                " VALUES (:contract, :goal, 1, '{}'::jsonb, :digest)"
                " ON CONFLICT (id) DO NOTHING"
            ),
            {"contract": CONTRACT, "goal": GOAL, "digest": DIGEST},
        )
        connection.execute(
            sa.text(
                "INSERT INTO panestria.task (id, goal_id, contract_id, name, state)"
                " VALUES (:task, :goal, :contract, :name, 'CREATED')"
            ),
            {"task": task_id, "goal": GOAL, "contract": CONTRACT, "name": name},
        )
        connection.execute(
            sa.text(
                "INSERT INTO panestria.task_attempt"
                " (id, task_id, attempt_number, lease_epoch, status, adapter)"
                " VALUES (:attempt, :task, 1, 0, 'PENDING', 'synthetic')"
            ),
            {"attempt": attempt_id, "task": task_id},
        )


def _effect_row(engine: sa.Engine, task_id: str) -> tuple[int, str, str, str]:
    with engine.connect() as connection:
        count = connection.execute(
            sa.text("SELECT count(*) FROM panestria.side_effect WHERE task_id = :task"),
            {"task": task_id},
        ).scalar_one()
        row = connection.execute(
            sa.text(
                "SELECT state, external_ref, reconciliation_note FROM panestria.side_effect"
                " WHERE task_id = :task AND effect_key = 'synthetic-observe'"
            ),
            {"task": task_id},
        ).one()
    return int(count), str(row[0]), str(row[1]), str(row[2])


def _workflow_status(engine: sa.Engine, workflow_id: str) -> str:
    with engine.connect() as connection:
        status = connection.execute(
            sa.text("SELECT status FROM dbos.workflow_status WHERE workflow_uuid = :workflow"),
            {"workflow": workflow_id},
        ).scalar_one()
    return str(status)


def _wait_database() -> None:
    deadline = time.monotonic() + 30
    while True:
        try:
            with psycopg.connect(DATABASE_URL, connect_timeout=2) as connection:
                connection.execute("SELECT 1")
            return
        except psycopg.Error:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.5)


def _snapshot(engine: sa.Engine, task_id: str, workflow_id: str) -> tuple[object, ...]:
    with engine.connect() as connection:
        task = connection.execute(
            sa.text("SELECT id::text, state, row_version FROM panestria.task WHERE id = :task"),
            {"task": task_id},
        ).one()
        effect = connection.execute(
            sa.text(
                "SELECT id::text, state, external_ref, reconciliation_note"
                " FROM panestria.side_effect WHERE task_id = :task"
            ),
            {"task": task_id},
        ).one()
        event = connection.execute(
            sa.text(
                "SELECT count(*), coalesce(max(seq), 0) FROM panestria.task_event WHERE task_id = :task"
            ),
            {"task": task_id},
        ).one()
        workflow = connection.execute(
            sa.text(
                "SELECT workflow_uuid::text, status, name FROM dbos.workflow_status"
                " WHERE workflow_uuid = :workflow"
            ),
            {"workflow": workflow_id},
        ).one()
    return (tuple(task), tuple(effect), tuple(event), tuple(workflow))


def test_uncommitted_external_step(
    database_url: str,
    record_property: pytest.RecordProperty,
    tmp_path: Path,
) -> None:
    _properties(record_property, "AOS-003-TC03")
    engine = sa.create_engine(sqlalchemy_url(database_url))
    try:
        _seed_task(engine, TASK_EFFECT, ATTEMPT_EFFECT, "effect")
        ready = tmp_path / "effect"
        running = _spawn(
            database_url,
            mode="effect",
            workflow_id="wf-effect-lost",
            task_id=TASK_EFFECT,
            crash_at="after-effect",
            ready=ready,
        )
        _wait_ready(ready, running)
        recorded = (1, "SUCCEEDED", f"synthetic:{TASK_EFFECT}", "recorded-before-checkpoint")
        assert _effect_row(engine, TASK_EFFECT) == recorded
        _kill(running)
        assert _effect_row(engine, TASK_EFFECT) == recorded
        recovered = _spawn(
            database_url,
            mode="recover",
            workflow_id="wf-effect-lost",
            task_id=TASK_EFFECT,
            crash_at=None,
            ready=None,
        )
        _finish(recovered)
        assert _effect_row(engine, TASK_EFFECT) == recorded
        assert _task_state(engine, TASK_EFFECT) == ("VALIDATING", 1, 1)
        assert _workflow_status(engine, "wf-effect-lost") == "SUCCESS"

        _seed_task(engine, TASK_FAIL, ATTEMPT_FAIL, "fail")
        failed = _spawn(
            database_url,
            mode="fail",
            workflow_id="wf-terminal-failure",
            task_id=TASK_FAIL,
            crash_at=None,
            ready=None,
        )
        _finish(failed)
        assert _task_state(engine, TASK_FAIL) == ("FAILED", 1, 1)
        assert _workflow_status(engine, "wf-terminal-failure") == "ERROR"
        again = _spawn(
            database_url,
            mode="fail",
            workflow_id="wf-terminal-failure",
            task_id=TASK_FAIL,
            crash_at=None,
            ready=None,
        )
        _finish(again)
        assert _task_state(engine, TASK_FAIL) == ("FAILED", 1, 1)
        assert _workflow_status(engine, "wf-terminal-failure") == "ERROR"
    finally:
        engine.dispose()


def test_database_restore_and_reconnect(
    database_url: str,
    record_property: pytest.RecordProperty,
    tmp_path: Path,
) -> None:
    _properties(record_property, "AOS-003-TC04")
    engine = sa.create_engine(sqlalchemy_url(database_url))
    try:
        _seed_task(engine, TASK_RESTORE, ATTEMPT_RESTORE, "restore")
        completed = _spawn(
            database_url,
            mode="effect",
            workflow_id="wf-restore",
            task_id=TASK_RESTORE,
            crash_at=None,
            ready=None,
        )
        _finish(completed)
        before = _snapshot(engine, TASK_RESTORE, "wf-restore")
    finally:
        engine.dispose()

    dumped = subprocess.run(
        [
            *COMPOSE,
            "exec",
            "-T",
            "-e",
            "PGPASSWORD=placeholder-not-a-secret",
            "postgres",
            "pg_dump",
            "-U",
            "panestria_synthetic",
            "-d",
            "panestria_synthetic",
            "-Fc",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    assert dumped.returncode == 0, dumped.stderr
    backup = tmp_path / "panestria.dump"
    backup.write_bytes(dumped.stdout)

    stopped = _run([*COMPOSE, "stop", "postgres"])
    assert stopped.returncode == 0, stopped.stderr
    try:
        with pytest.raises(sa.exc.OperationalError):
            connect_for_admission(database_url)
    finally:
        started = _run([*COMPOSE, "up", "-d", "--wait", "postgres"])
        assert started.returncode == 0, started.stderr
    _wait_database()
    engine = sa.create_engine(sqlalchemy_url(database_url))
    try:
        assert _snapshot(engine, TASK_RESTORE, "wf-restore") == before
    finally:
        engine.dispose()

    removed = _run([*COMPOSE, "down", "-v"])
    assert removed.returncode == 0, removed.stderr
    restored_up = _run([*COMPOSE, "up", "-d", "--wait", "postgres"])
    assert restored_up.returncode == 0, restored_up.stderr
    _wait_database()
    payload = backup.read_bytes()
    restored = subprocess.run(
        [
            *COMPOSE,
            "exec",
            "-T",
            "-e",
            "PGPASSWORD=placeholder-not-a-secret",
            "postgres",
            "pg_restore",
            "-U",
            "panestria_synthetic",
            "-d",
            "panestria_synthetic",
            "--no-owner",
            "--exit-on-error",
        ],
        cwd=ROOT,
        input=payload,
        capture_output=True,
        check=False,
    )
    assert restored.returncode == 0, restored.stderr
    engine = sa.create_engine(sqlalchemy_url(database_url))
    try:
        assert _snapshot(engine, TASK_RESTORE, "wf-restore") == before
    finally:
        engine.dispose()

