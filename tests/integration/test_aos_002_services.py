"""AOS-002-TC03 and TC04. Scoped writes, DAG checks, and PostgreSQL concurrency."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import psycopg
import pytest

from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor, GoalService
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.tasks import DagRejected, TaskService, validate_dag
from panestria.kernel.uow import UnitOfWork
from stack_support import COMPOSE, DATABASE_URL

ROOT = Path(__file__).resolve().parents[2]


FIXTURE = ROOT / "docs" / "fixtures" / "synthetic-goal-contract.json"
OWNER = "00000000-0000-4000-8000-000000000002"
OTHER = "00000000-0000-4000-8000-000000000099"
PROJECT = "00000000-0000-4000-8000-000000000003"
GOAL = "00000000-0000-4000-8000-000000000001"
TASK_A = "00000000-0000-4000-8000-0000000000a1"
TASK_B = "00000000-0000-4000-8000-0000000000b2"
POLICY = "synthetic-approve-first-v1"
CORRELATION = "00000000-0000-4000-8000-0000000000c1"


def _run(argv: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=ROOT, env=env, text=True, capture_output=True, check=False)


def _contract() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return loaded


def _properties(record_property: pytest.RecordProperty, case_id: str, lane: str) -> None:
    commit = _run(["git", "rev-parse", "HEAD"]).stdout.strip()
    dirty = bool(_run(["git", "status", "--porcelain"]).stdout.strip())
    record_property("gate_case_id", case_id)
    record_property("candidate_commit", commit)
    record_property("fixture_digest", hashlib.sha256(FIXTURE.read_bytes()).hexdigest())
    record_property("lane", lane)
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


@pytest.fixture(autouse=True)
def _empty(database_url: str) -> None:
    with psycopg.connect(database_url) as connection:
        connection.execute("TRUNCATE panestria.principal RESTART IDENTITY CASCADE")
        connection.commit()


def _connect(database_url: str) -> psycopg.Connection[tuple[Any, ...]]:
    return psycopg.connect(database_url)


def _seed_scope(connection: psycopg.Connection[tuple[Any, ...]]) -> None:
    connection.execute(
        "INSERT INTO panestria.principal (id, display_name) VALUES (%s, 'owner'), (%s, 'other')",
        (OWNER, OTHER),
    )
    connection.execute(
        "INSERT INTO panestria.project (id, owner_id) VALUES (%s, %s)",
        (PROJECT, OWNER),
    )


def _seed_tasks(connection: psycopg.Connection[tuple[Any, ...]]) -> None:
    contract_id = connection.execute(
        "SELECT id FROM panestria.goal_contract WHERE goal_id = %s",
        (GOAL,),
    ).fetchone()
    assert contract_id is not None
    connection.execute(
        "INSERT INTO panestria.task (id, goal_id, contract_id, name, state)"
        " VALUES (%s, %s, %s, 'left', 'CREATED'), (%s, %s, %s, 'right', 'CREATED')",
        (TASK_A, GOAL, contract_id[0], TASK_B, GOAL, contract_id[0]),
    )


def _wait_for_event_lock() -> None:
    deadline = time.monotonic() + 5
    with psycopg.connect(DATABASE_URL, autocommit=True) as watch:
        while time.monotonic() < deadline:
            waiting = watch.execute(
                "SELECT count(*) FROM pg_stat_activity"
                " WHERE wait_event_type = 'Lock' AND query LIKE %s",
                ("%pg_advisory_xact_lock%",),
            ).fetchone()
            if waiting is not None and int(waiting[0]) >= 1:
                return
            time.sleep(0.05)
    raise AssertionError("second writer did not wait on the event lock")


def test_concurrent_transition_and_cursor(
    database_url: str,
    record_property: pytest.RecordProperty,
) -> None:
    _properties(record_property, "AOS-002-TC03", "integration")
    validate_dag([TASK_A, TASK_B], [(TASK_A, TASK_B)])
    with pytest.raises(DagRejected) as duplicate:
        validate_dag([TASK_A, TASK_A], [])
    assert duplicate.value.code == "duplicate_node"
    with pytest.raises(DagRejected) as self_link:
        validate_dag([TASK_A], [(TASK_A, TASK_A)])
    assert self_link.value.code == "self_link"
    with pytest.raises(DagRejected) as unknown:
        validate_dag([TASK_A], [(TASK_A, TASK_B)])
    assert unknown.value.code == "unknown_node"
    with pytest.raises(DagRejected) as cycle:
        validate_dag([TASK_A, TASK_B], [(TASK_A, TASK_B), (TASK_B, TASK_A)])
    assert cycle.value.code == "cycle"

    actor = Actor(OWNER, PROJECT)
    goals = GoalService()
    tasks = TaskService()
    with _connect(database_url) as connection:
        _seed_scope(connection)
        receipt = goals.submit(UnitOfWork(connection), actor, _contract(), "submit-1")
        connection.commit()
    assert receipt.replayed is False
    assert receipt.goal_id == GOAL

    with _connect(database_url) as connection:
        _seed_tasks(connection)
        connection.commit()
        with pytest.raises(DagRejected) as stored_self:
            tasks.set_dependencies(UnitOfWork(connection), actor, [(TASK_A, TASK_A)])
        assert stored_self.value.code == "self_link"
        connection.rollback()
        with pytest.raises(DagRejected) as stored_cycle:
            tasks.set_dependencies(UnitOfWork(connection), actor, [(TASK_A, TASK_B), (TASK_B, TASK_A)])
        assert stored_cycle.value.code == "cycle"
        connection.rollback()
        tasks.set_dependencies(UnitOfWork(connection), actor, [(TASK_A, TASK_B)])
        connection.commit()
        stored = connection.execute("SELECT count(*) FROM panestria.task_dependency").fetchone()
        assert stored == (1,)

    with _connect(database_url) as connection:
        with pytest.raises(KernelDenied) as illegal:
            tasks.transition(
                UnitOfWork(connection),
                actor,
                TASK_A,
                0,
                0,
                "COMPLETED",
                "skip",
                policy_version=POLICY,
                correlation_id=CORRELATION,
            )
        assert illegal.value.code == "illegal_transition"
        connection.rollback()

    held = _connect(database_url)
    try:
        tasks.transition(
            UnitOfWork(held),
            actor,
            TASK_A,
            0,
            0,
            "VALIDATING",
            "local",
            policy_version=POLICY,
            correlation_id=CORRELATION,
        )
        with _connect(database_url) as other:
            visible = other.execute("SELECT state FROM panestria.task WHERE id = %s", (TASK_A,)).fetchone()
        assert visible == ("CREATED",)
    finally:
        held.rollback()
        held.close()

    outcomes: list[object] = []
    barrier = threading.Barrier(2)

    def _mutate() -> None:
        connection = _connect(database_url)
        try:
            barrier.wait(5)
            receipt_or_code: object
            try:
                receipt_or_code = tasks.transition(
                    UnitOfWork(connection),
                    actor,
                    TASK_A,
                    0,
                    0,
                    "VALIDATING",
                    "race",
                    policy_version=POLICY,
                    correlation_id=CORRELATION,
                )
                connection.commit()
            except KernelDenied as exc:
                connection.rollback()
                receipt_or_code = exc.code
            outcomes.append(receipt_or_code)
        finally:
            connection.close()

    threads = [threading.Thread(target=_mutate) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert sorted(type(item).__name__ for item in outcomes) == ["TransitionReceipt", "str"]
    assert "version_conflict" in outcomes
    with _connect(database_url) as connection:
        winner = connection.execute(
            "SELECT state, row_version FROM panestria.task WHERE id = %s",
            (TASK_A,),
        ).fetchone()
        events = connection.execute(
            "SELECT count(*) FROM panestria.task_event WHERE kind = 'task.transition'"
        ).fetchone()
    assert winner == ("VALIDATING", 1)
    assert events == (1,)

    with _connect(database_url) as connection:
        connection.execute("TRUNCATE panestria.task_event RESTART IDENTITY")
        connection.commit()
    _assert_commit_order(database_url)
    _assert_rollback_gap(database_url)

    changed = _contract()
    changed["intent"] = "A different synthetic intent that must not replace the first."
    with _connect(database_url) as connection:
        replay = goals.submit(UnitOfWork(connection), actor, _contract(), "submit-1")
        connection.commit()
    assert replay.replayed is True
    assert replay.contract_sha256 == receipt.contract_sha256
    with _connect(database_url) as connection:
        with pytest.raises(KernelDenied) as conflict:
            goals.submit(UnitOfWork(connection), actor, changed, "submit-1")
        assert conflict.value.code == "idempotency_conflict"
        connection.rollback()
        count = connection.execute("SELECT count(*) FROM panestria.goal").fetchone()
    assert count == (1,)


def _assert_commit_order(database_url: str) -> None:
    started = threading.Event()
    finished = threading.Event()
    errors: list[BaseException] = []

    def _second() -> None:
        connection = _connect(database_url)
        try:
            started.wait(5)
            append_event(
                UnitOfWork(connection),
                goal_id=GOAL,
                task_id=None,
                kind="goal.cursor",
                actor=OWNER,
                payload={"writer": "second"},
            )
            connection.commit()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
            connection.rollback()
        finally:
            connection.close()
            finished.set()

    thread = threading.Thread(target=_second)
    thread.start()
    first = _connect(database_url)
    try:
        append_event(
            UnitOfWork(first),
            goal_id=GOAL,
            task_id=None,
            kind="goal.cursor",
            actor=OWNER,
            payload={"writer": "first"},
        )
        started.set()
        _wait_for_event_lock()
        first.commit()
    finally:
        first.close()
    assert finished.wait(5)
    thread.join(5)
    assert errors == []
    with _connect(database_url) as connection:
        rows = connection.execute(
            "SELECT seq, payload->>'writer' FROM panestria.task_event ORDER BY seq"
        ).fetchall()
    assert rows == [(1, "first"), (2, "second")]


def _assert_rollback_gap(database_url: str) -> None:
    with _connect(database_url) as connection:
        connection.execute("TRUNCATE panestria.task_event RESTART IDENTITY")
        connection.commit()
    started = threading.Event()
    finished = threading.Event()
    errors: list[BaseException] = []

    def _second() -> None:
        connection = _connect(database_url)
        try:
            started.wait(5)
            append_event(
                UnitOfWork(connection),
                goal_id=GOAL,
                task_id=None,
                kind="goal.cursor",
                actor=OWNER,
                payload={"writer": "kept"},
            )
            connection.commit()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
            connection.rollback()
        finally:
            connection.close()
            finished.set()

    thread = threading.Thread(target=_second)
    thread.start()
    first = _connect(database_url)
    try:
        append_event(
            UnitOfWork(first),
            goal_id=GOAL,
            task_id=None,
            kind="goal.cursor",
            actor=OWNER,
            payload={"writer": "rolled-back"},
        )
        started.set()
        _wait_for_event_lock()
        first.rollback()
    finally:
        first.close()
    assert finished.wait(5)
    thread.join(5)
    assert errors == []
    with _connect(database_url) as connection:
        rows = connection.execute(
            "SELECT seq, payload->>'writer' FROM panestria.task_event ORDER BY seq"
        ).fetchall()
    assert rows == [(2, "kept")]


def test_foreign_scope_and_mass_assignment(
    database_url: str,
    record_property: pytest.RecordProperty,
) -> None:
    _properties(record_property, "AOS-002-TC04", "security")
    actor = Actor(OWNER, PROJECT)
    stranger = Actor(OTHER, PROJECT)
    goals = GoalService()
    tasks = TaskService()
    with _connect(database_url) as connection:
        _seed_scope(connection)
        goals.submit(UnitOfWork(connection), actor, _contract(), "submit-scope")
        connection.commit()
        _seed_tasks(connection)
        connection.commit()

    with _connect(database_url) as connection:
        visible = goals.get(UnitOfWork(connection), actor, GOAL)
        assert visible.goal_id == GOAL
        with pytest.raises(KernelDenied) as hidden:
            goals.get(UnitOfWork(connection), stranger, GOAL)
        assert hidden.value.code == "not_found"
        with pytest.raises(KernelDenied) as foreign_write:
            tasks.transition(
                UnitOfWork(connection),
                stranger,
                TASK_A,
                0,
                0,
                "VALIDATING",
                "foreign",
                policy_version=POLICY,
                correlation_id=CORRELATION,
            )
        assert foreign_write.value.code == "not_found"
        connection.rollback()
        state = connection.execute(
            "SELECT state, row_version FROM panestria.task WHERE id = %s",
            (TASK_A,),
        ).fetchone()
    assert state == ("CREATED", 0)

    mismatched = _contract()
    mismatched["owner_id"] = OTHER
    approved = _contract()
    approved["approved_by"] = OWNER
    granted = _contract()
    granted["policy_granted"] = True
    executable = _contract()
    executable["acceptance"][0]["verifier"]["run"] = "echo unsafe"
    with _connect(database_url) as connection:
        for payload, code in (
            (mismatched, "not_found"),
            (approved, "invalid_contract"),
            (granted, "invalid_contract"),
            (executable, "legacy_verifier"),
        ):
            with pytest.raises(KernelDenied) as denied:
                goals.submit(UnitOfWork(connection), actor, payload, "rejected-" + code)
            assert denied.value.code == code
            connection.rollback()
        rows = connection.execute(
            "SELECT count(*), count(approved_by) FROM panestria.goal_contract"
        ).fetchone()
    assert rows == (1, 0)


def test_transition_binds_policy_and_correlation(
    database_url: str,
    record_property: pytest.RecordProperty,
) -> None:
    _properties(record_property, "AOS-002-TC04", "security")
    actor = Actor(OWNER, PROJECT)
    goals = GoalService()
    tasks = TaskService()
    with _connect(database_url) as connection:
        _seed_scope(connection)
        goals.submit(UnitOfWork(connection), actor, _contract(), "submit-policy")
        connection.commit()
        _seed_tasks(connection)
        connection.commit()
        with pytest.raises(KernelDenied) as mismatched:
            tasks.transition(
                UnitOfWork(connection),
                actor,
                TASK_A,
                0,
                0,
                "VALIDATING",
                "downgrade",
                policy_version="other-policy",
                correlation_id=CORRELATION,
            )
        assert mismatched.value.code == "policy_mismatch"
        connection.rollback()
        with pytest.raises(KernelDenied) as malformed:
            tasks.transition(
                UnitOfWork(connection),
                actor,
                TASK_A,
                0,
                0,
                "VALIDATING",
                "blank",
                policy_version=POLICY,
                correlation_id="not-a-correlation",
            )
        assert malformed.value.code == "invalid_correlation"
        connection.rollback()
        unchanged = connection.execute(
            "SELECT state, row_version FROM panestria.task WHERE id = %s",
            (TASK_A,),
        ).fetchone()
        denied_events = connection.execute(
            "SELECT count(*) FROM panestria.task_event WHERE kind = 'task.transition'"
        ).fetchone()
        assert unchanged == ("CREATED", 0)
        assert denied_events == (0,)
        held = _connect(database_url)
        try:
            tasks.transition(
                UnitOfWork(held),
                actor,
                TASK_A,
                0,
                0,
                "VALIDATING",
                "bound",
                policy_version=POLICY,
                correlation_id=CORRELATION,
            )
            visible = connection.execute(
                "SELECT state FROM panestria.task WHERE id = %s",
                (TASK_A,),
            ).fetchone()
            leaked = connection.execute(
                "SELECT count(*) FROM panestria.task_event WHERE kind = 'task.transition'"
            ).fetchone()
            assert visible == ("CREATED",)
            assert leaked == (0,)
        finally:
            held.rollback()
            held.close()
        tasks.transition(
            UnitOfWork(connection),
            actor,
            TASK_A,
            0,
            0,
            "VALIDATING",
            "bound",
            policy_version=POLICY,
            correlation_id=CORRELATION,
        )
        connection.commit()
        recorded = connection.execute(
            "SELECT state, payload->>'policy_version', payload->>'correlation_id', trace_id"
            " FROM panestria.task AS task"
            " JOIN panestria.task_event AS event ON event.task_id = task.id"
            " WHERE task.id = %s AND event.kind = 'task.transition'",
            (TASK_A,),
        ).fetchone()
    assert recorded == ("VALIDATING", POLICY, CORRELATION, CORRELATION)
