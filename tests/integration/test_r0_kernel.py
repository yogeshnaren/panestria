"""R0-08, R0-09, and R0-10. Stored cycles, concurrent submit, and malformed envelopes."""

from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from panestria.api.auth import GoalApi
from panestria.api.main import create_app, mount_goal_api
from panestria.config import Settings
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor, GoalReceipt, GoalService
from panestria.kernel.tasks import DagRejected, TaskService
from panestria.kernel.uow import UnitOfWork
from stack_support import COMPOSE, DATABASE_URL

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "docs" / "fixtures" / "synthetic-goal-contract.json"


TOKEN = "synthetic-loopback-token"
OWNER = "00000000-0000-4000-8000-000000000002"
PROJECT = "00000000-0000-4000-8000-000000000003"
GOAL = "00000000-0000-4000-8000-000000000031"
OTHER_GOAL = "00000000-0000-4000-8000-000000000032"
RACE_GOAL = "00000000-0000-4000-8000-000000000033"
TASK_A = "00000000-0000-4000-8000-0000000000a1"
TASK_B = "00000000-0000-4000-8000-0000000000b2"
TASK_C = "00000000-0000-4000-8000-0000000000c3"
TASK_D = "00000000-0000-4000-8000-0000000000d5"
TASK_E = "00000000-0000-4000-8000-0000000000e6"
FOREIGN = "00000000-0000-4000-8000-0000000000d4"


def _database() -> None:
    global DATABASE_URL
    subprocess.run([*COMPOSE, "down", "-v"], check=False)
    # A fixed test listener can collide with another service or client port.
    # Docker reserves an available loopback endpoint atomically; discover that
    # actual endpoint, rather than probing/closing a host socket before bind.
    env = {**os.environ, "R0_TEST_DATABASE_PORT": "0"}
    up = subprocess.run(
        [*COMPOSE, "up", "-d", "--wait"], cwd=ROOT, env=env, text=True, capture_output=True, check=False
    )
    assert up.returncode == 0, up.stderr
    published = subprocess.run(
        [*COMPOSE, "port", "postgres", "5432"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    host, port = published.rsplit(":", 1)
    assert host == "127.0.0.1" and port.isdecimal() and 0 < int(port) <= 65535
    DATABASE_URL = f"postgresql://panestria_synthetic:placeholder-not-a-secret@127.0.0.1:{port}/panestria_synthetic"
    upgraded = subprocess.run(
        ["uv", "run", "--frozen", "alembic", "-c", "migrations/alembic.ini", "upgrade", "head"],
        cwd=ROOT,
        env={**os.environ, "PANESTRIA_DATABASE_URL": DATABASE_URL},
        text=True,
        capture_output=True,
        check=False,
    )
    assert upgraded.returncode == 0, upgraded.stderr


def _document(goal_id: str, intent: str = "synthetic") -> dict[str, object]:
    document: dict[str, object] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["goal_id"] = goal_id
    document["intent"] = intent
    return document


def _client() -> TestClient:
    settings = Settings(
        schema_version=1,
        profile="SYNTHETIC_DEV",
        bind_host="127.0.0.1",
        bind_port=8765,
        readiness_budget_ms=500,
        database_url=DATABASE_URL,  # type: ignore[arg-type]
    )
    application = create_app(settings, lambda _deadline: None)  # type: ignore[arg-type, return-value]
    mount_goal_api(application, GoalApi(TOKEN, OWNER, PROJECT, DATABASE_URL))
    return TestClient(application, base_url="http://127.0.0.1")


def test_graph_idempotency_and_malformed_acceptance(record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-002-TC03")
    record_property("also_covers", "AOS-002-TC04")
    _database()
    actor = Actor(OWNER, PROJECT)
    goals = GoalService()
    tasks = TaskService()
    try:
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute("INSERT INTO panestria.principal (id, display_name) VALUES (%s, 'owner')", (OWNER,))
            connection.execute("INSERT INTO panestria.project (id, owner_id) VALUES (%s, %s)", (PROJECT, OWNER))
            connection.commit()
            goals.submit(UnitOfWork(connection), actor, _document(GOAL), "graph")
            goals.submit(UnitOfWork(connection), actor, _document(OTHER_GOAL), "other-goal")
            connection.commit()
            contract = connection.execute(
                "SELECT id FROM panestria.goal_contract WHERE goal_id = %s",
                (GOAL,),
            ).fetchone()
            other_contract = connection.execute(
                "SELECT id FROM panestria.goal_contract WHERE goal_id = %s",
                (OTHER_GOAL,),
            ).fetchone()
            assert contract is not None and other_contract is not None
            connection.execute(
                "INSERT INTO panestria.task (id, goal_id, contract_id, name, state) VALUES"
                " (%s, %s, %s, 'a', 'CREATED'), (%s, %s, %s, 'b', 'CREATED'),"
                " (%s, %s, %s, 'c', 'CREATED'), (%s, %s, %s, 'd', 'CREATED'),"
                " (%s, %s, %s, 'e', 'CREATED')",
                (
                    TASK_A,
                    GOAL,
                    contract[0],
                    TASK_B,
                    GOAL,
                    contract[0],
                    TASK_C,
                    GOAL,
                    contract[0],
                    TASK_D,
                    GOAL,
                    contract[0],
                    TASK_E,
                    GOAL,
                    contract[0],
                ),
            )
            connection.execute(
                "INSERT INTO panestria.task (id, goal_id, contract_id, name, state)"
                " VALUES (%s, %s, %s, 'foreign', 'CREATED')",
                (FOREIGN, OTHER_GOAL, other_contract[0]),
            )
            connection.commit()
            tasks.set_dependencies(UnitOfWork(connection), actor, [(TASK_A, TASK_B)])
            connection.commit()
            with pytest.raises(DagRejected) as reverse:
                tasks.set_dependencies(UnitOfWork(connection), actor, [(TASK_B, TASK_A)])
            assert reverse.value.code == "cycle"
            connection.rollback()
            tasks.set_dependencies(UnitOfWork(connection), actor, [(TASK_B, TASK_C)])
            connection.commit()
            with pytest.raises(DagRejected) as triangle:
                tasks.set_dependencies(UnitOfWork(connection), actor, [(TASK_C, TASK_A)])
            assert triangle.value.code == "cycle"
            connection.rollback()
            tasks.set_dependencies(UnitOfWork(connection), actor, [(TASK_A, TASK_B), (TASK_A, TASK_B)])
            connection.commit()
            stored = connection.execute("SELECT count(*) FROM panestria.task_dependency").fetchone()
            assert stored == (2,)
            with psycopg.connect(DATABASE_URL) as foreign_conn:
                try:
                    tasks.set_dependencies(UnitOfWork(foreign_conn), actor, [(TASK_A, FOREIGN)])
                    foreign_conn.commit()
                    raise AssertionError("foreign endpoint was stored")
                except KernelDenied as exc:
                    foreign_conn.rollback()
                    assert exc.code == "not_found"
            _concurrent_cycle(tasks, actor)
            count = connection.execute("SELECT count(*) FROM panestria.task_dependency").fetchone()
            assert count == (3,)

            with pytest.raises(KernelDenied) as same_goal:
                goals.submit(UnitOfWork(connection), actor, _document(GOAL, "changed"), "different-key")
            assert same_goal.value.code == "idempotency_conflict"
            connection.rollback()
            with pytest.raises(KernelDenied) as changed:
                goals.submit(UnitOfWork(connection), actor, _document(GOAL, "changed"), "graph")
            assert changed.value.code == "idempotency_conflict"
            connection.rollback()

        receipts: list[GoalReceipt] = []
        barrier = threading.Barrier(2)

        def _submit() -> None:
            with psycopg.connect(DATABASE_URL) as connection:
                barrier.wait(5)
                receipt = goals.submit(UnitOfWork(connection), actor, _document(RACE_GOAL), "race")
                connection.commit()
                receipts.append(receipt)

        threads = [threading.Thread(target=_submit) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        assert sorted(item.replayed for item in receipts) == [False, True]
        assert {item.goal_id for item in receipts} == {RACE_GOAL}
        with psycopg.connect(DATABASE_URL) as connection:
            goals_count = connection.execute(
                "SELECT count(*) FROM panestria.goal WHERE id = %s",
                (RACE_GOAL,),
            ).fetchone()
            contracts = connection.execute(
                "SELECT count(*) FROM panestria.goal_contract WHERE goal_id = %s",
                (RACE_GOAL,),
            ).fetchone()
            events = connection.execute(
                "SELECT count(*) FROM panestria.task_event WHERE goal_id = %s AND kind = 'goal.submitted'",
                (RACE_GOAL,),
            ).fetchone()
        assert goals_count == (1,)
        assert contracts == (1,)
        assert events == (1,)

        with _client() as client:
            for value in (None, 42, True, {"id": "AC-BAD"}):
                document = _document("00000000-0000-4000-8000-000000000099")
                document["acceptance"] = value
                response = client.post(
                    "/v1/goals",
                    content=json.dumps(document),
                    headers={"authorization": f"Bearer {TOKEN}", "idempotency-key": f"bad-{value!r}"},
                )
                assert response.status_code == 422
                body = response.json()
                assert body["code"] == "invalid_contract"
                assert body["message"] == "invalid_contract"
                echoed = json.dumps({"code": body["code"], "message": body["message"]})
                assert "42" not in echoed
                assert "AC-BAD" not in echoed
                assert "true" not in echoed
                assert "null" not in echoed
            document = _document("00000000-0000-4000-8000-000000000098")
            document["acceptance"] = [42]
            response = client.post(
                "/v1/goals",
                content=json.dumps(document),
                headers={"authorization": f"Bearer {TOKEN}", "idempotency-key": "bad-list"},
            )
            assert response.status_code == 422
            listed = response.json()
            assert listed["code"] == "invalid_contract"
            assert listed["message"] == "invalid_contract"
            assert "42" not in json.dumps({"code": listed["code"], "message": listed["message"]})
        with psycopg.connect(DATABASE_URL) as connection:
            leaked = connection.execute(
                "SELECT count(*) FROM panestria.goal WHERE id IN (%s, %s)",
                ("00000000-0000-4000-8000-000000000099", "00000000-0000-4000-8000-000000000098"),
            ).fetchone()
        assert leaked == (0,)
    finally:
        subprocess.run([*COMPOSE, "down", "-v"], check=False)


def _concurrent_cycle(tasks: TaskService, actor: Actor) -> None:
    barrier = threading.Barrier(2)
    errors: list[str] = []

    def _add(edge: tuple[str, str]) -> None:
        with psycopg.connect(DATABASE_URL) as connection:
            barrier.wait(5)
            try:
                tasks.set_dependencies(UnitOfWork(connection), actor, [edge])
                connection.commit()
            except DagRejected as exc:
                connection.rollback()
                errors.append(exc.code)

    threads = [
        threading.Thread(target=_add, args=((TASK_D, TASK_E),)),
        threading.Thread(target=_add, args=((TASK_E, TASK_D),)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert errors == ["cycle"]
