"""R0-03. Admission enqueues the registered workflow and a queue consumer runs it."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path

import psycopg
import pytest

from panestria.execution.dbos_runtime import QUEUE_NAME
from panestria.execution.synthetic_journey import SyntheticJourney
from panestria.kernel.approvals import ApprovalService
from panestria.kernel.goals import Actor, GoalService
from panestria.kernel.uow import UnitOfWork

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "docs" / "fixtures" / "synthetic-goal-contract.json"
COMPOSE = ["docker", "compose", "-f", str(ROOT / "compose.yaml"), "-p", "panestria-s3"]
DATABASE_URL = "postgresql://panestria_synthetic:placeholder-not-a-secret@127.0.0.1:55432/panestria_synthetic"
OWNER = "00000000-0000-4000-8000-000000000002"
PROJECT = "00000000-0000-4000-8000-000000000003"


def _database() -> None:
    os.environ["PANESTRIA_DATABASE_URL"] = DATABASE_URL
    subprocess.run([*COMPOSE, "down", "-v"], check=False)
    up = subprocess.run([*COMPOSE, "up", "-d", "--wait"], cwd=ROOT, text=True, capture_output=True, check=False)
    assert up.returncode == 0, up.stderr
    upgraded = subprocess.run(
        ["uv", "run", "--frozen", "alembic", "-c", "migrations/alembic.ini", "upgrade", "head"],
        cwd=ROOT,
        env={**os.environ, "PANESTRIA_DATABASE_URL": DATABASE_URL},
        text=True,
        capture_output=True,
        check=False,
    )
    assert upgraded.returncode == 0, upgraded.stderr


def _submit(connection: psycopg.Connection[object], goals: GoalService, goal_id: str) -> str:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["goal_id"] = goal_id
    receipt = goals.submit(UnitOfWork(connection), Actor(OWNER, PROJECT), document, goal_id)
    connection.commit()
    return receipt.goal_id


def _spawn(workflow_id: str, crash_at: str | None, ready: Path | None) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["PANESTRIA_DATABASE_URL"] = DATABASE_URL
    env["PANESTRIA_MODE"] = "consume"
    env["PANESTRIA_WORKFLOW_ID"] = workflow_id
    env.pop("PANESTRIA_CRASH_AT", None)
    env.pop("PANESTRIA_READY_FILE", None)
    env.pop("PANESTRIA_DEFER_CONSUME", None)
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
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if path.exists():
            return
        if process.poll() is not None:
            stderr = process.stderr.read() if process.stderr is not None else ""
            raise AssertionError(stderr)
        time.sleep(0.1)
    raise AssertionError("crash gate was not reached")


def _kill(process: subprocess.Popen[str]) -> None:
    os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=5)


def _finish(process: subprocess.Popen[str]) -> None:
    stdout, stderr = process.communicate(timeout=50)
    if process.returncode != 0:
        raise AssertionError(stderr or stdout)


def test_admitted_queue_restarts_at_transaction_worker_and_verification(
    tmp_path: Path, record_property: pytest.RecordProperty
) -> None:
    record_property("gate_case_id", "AOS-003-TC02")
    _database()
    os.environ["PANESTRIA_DEFER_CONSUME"] = "1"
    journey = SyntheticJourney()
    approvals = ApprovalService()
    goals = GoalService()
    actor = Actor(OWNER, PROJECT)
    try:
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute("INSERT INTO panestria.principal (id, display_name) VALUES (%s, 'owner')", (OWNER,))
            connection.execute("INSERT INTO panestria.project (id, owner_id) VALUES (%s, %s)", (PROJECT, OWNER))
            connection.commit()
        points = ("before-commit", "before-worker", "before-verify")
        for index, point in enumerate(points):
            goal_id = f"00000000-0000-4000-8000-0000000000{index + 1:02d}"
            sandbox = tmp_path / point
            with psycopg.connect(DATABASE_URL) as connection:
                submitted = _submit(connection, goals, goal_id)
                opened = journey.open_contract_wait(connection, actor, submitted, sandbox)
                assert opened.attempts == 0
                assert opened.approval_id is not None
                approvals.decide(
                    UnitOfWork(connection),
                    actor,
                    opened.approval_id,
                    str(opened.effect_digest),
                    int(opened.expected_version or 0),
                    "approve",
                    f"consent-{point}",
                )
                connection.commit()
                journey.resume(connection, actor, submitted, sandbox)
                link = connection.execute(
                    "SELECT link.dbos_workflow_id, task.state, attempt.status"
                    " FROM panestria.workflow_link AS link"
                    " JOIN panestria.task AS task ON task.id = link.task_id"
                    " JOIN panestria.task_attempt AS attempt ON attempt.id = link.attempt_id"
                    " WHERE task.goal_id = %s",
                    (submitted,),
                ).fetchone()
            assert link is not None
            workflow_id, state, status = link
            assert state == "READY"
            assert status == "PENDING"
            with psycopg.connect(DATABASE_URL) as connection:
                queued = connection.execute(
                    "SELECT queue_name, status, inputs FROM dbos.workflow_status WHERE workflow_uuid = %s",
                    (workflow_id,),
                ).fetchone()
            assert queued is not None
            assert queued[0] == QUEUE_NAME
            assert queued[1] == "ENQUEUED"
            crashed = _spawn(str(workflow_id), point, tmp_path / f"{point}.ready")
            _wait_ready(tmp_path / f"{point}.ready", crashed)
            _kill(crashed)
            with psycopg.connect(DATABASE_URL) as connection:
                mid = connection.execute(
                    "SELECT goal.status, count(attempt.id)"
                    " FROM panestria.goal AS goal"
                    " JOIN panestria.task AS task ON task.goal_id = goal.id"
                    " JOIN panestria.task_attempt AS attempt ON attempt.task_id = task.id"
                    " WHERE goal.id = %s GROUP BY goal.status",
                    (submitted,),
                ).fetchone()
            assert mid is not None
            assert mid[0] != "COMPLETED"
            assert int(mid[1]) == 1
            recovered = _spawn(str(workflow_id), None, None)
            _finish(recovered)
            with psycopg.connect(DATABASE_URL) as connection:
                done = connection.execute(
                    "SELECT goal.status, task.state, attempt.status, count(attempt.id),"
                    " workflow.status, workflow.queue_name"
                    " FROM panestria.goal AS goal"
                    " JOIN panestria.task AS task ON task.goal_id = goal.id"
                    " JOIN panestria.task_attempt AS attempt ON attempt.task_id = task.id"
                    " JOIN panestria.workflow_link AS link ON link.attempt_id = attempt.id"
                    " JOIN dbos.workflow_status AS workflow ON workflow.workflow_uuid = link.dbos_workflow_id"
                    " WHERE goal.id = %s"
                    " GROUP BY goal.status, task.state, attempt.status, workflow.status, workflow.queue_name",
                    (submitted,),
                ).fetchone()
                checks = connection.execute(
                    "SELECT count(*) FROM panestria.check_run AS run"
                    " JOIN panestria.task AS task ON task.id = run.task_id"
                    " WHERE task.goal_id = %s AND run.evidence_artifact_id IS NOT NULL",
                    (submitted,),
                ).fetchone()
                artifacts = connection.execute(
                    "SELECT count(*) FROM panestria.artifact AS artifact"
                    " JOIN panestria.task AS task ON task.id = artifact.task_id"
                    " WHERE task.goal_id = %s AND artifact.kind = 'candidate'",
                    (submitted,),
                ).fetchone()
                effects = connection.execute(
                    "SELECT count(*) FROM panestria.side_effect AS effect"
                    " JOIN panestria.task AS task ON task.id = effect.task_id"
                    " WHERE task.goal_id = %s",
                    (submitted,),
                ).fetchone()
            assert done is not None
            assert done[0] != "COMPLETED"
            assert done[1] == "WAITING_APPROVAL"
            assert done[2] == "SUCCEEDED"
            assert int(done[3]) == 1
            assert done[4] == "SUCCESS"
            assert done[5] == QUEUE_NAME
            assert checks is not None and int(checks[0]) >= 1
            assert artifacts is not None and int(artifacts[0]) == 1
            assert effects is not None and int(effects[0]) == 0
    finally:
        os.environ.pop("PANESTRIA_DEFER_CONSUME", None)
        subprocess.run([*COMPOSE, "down", "-v"], check=False)


def test_repeated_recovery_stops_and_fails_the_task(tmp_path: Path, record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-003-TC03")
    _database()
    os.environ["PANESTRIA_DEFER_CONSUME"] = "1"
    journey = SyntheticJourney()
    approvals = ApprovalService()
    goals = GoalService()
    actor = Actor(OWNER, PROJECT)
    goal_id = "00000000-0000-4000-8000-0000000000e3"
    try:
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute(
                "INSERT INTO panestria.principal (id, display_name) VALUES (%s, 'owner')",
                (OWNER,),
            )
            connection.execute(
                "INSERT INTO panestria.project (id, owner_id) VALUES (%s, %s)",
                (PROJECT, OWNER),
            )
            connection.commit()
            submitted = _submit(connection, goals, goal_id)
            opened = journey.open_contract_wait(connection, actor, submitted, tmp_path / "limit")
            assert opened.approval_id is not None
            approvals.decide(
                UnitOfWork(connection),
                actor,
                opened.approval_id,
                str(opened.effect_digest),
                int(opened.expected_version or 0),
                "approve",
                "consent-limit",
            )
            connection.commit()
            journey.resume(connection, actor, submitted, tmp_path / "limit")
            link = connection.execute(
                "SELECT link.dbos_workflow_id::text FROM panestria.workflow_link AS link"
                " JOIN panestria.task AS task ON task.id = link.task_id WHERE task.goal_id = %s",
                (submitted,),
            ).fetchone()
        assert link is not None
        workflow_id = str(link[0])
        stopped = False
        for index in range(8):
            ready = tmp_path / f"limit-{index}.ready"
            process = _spawn(workflow_id, "before-commit", ready)
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline and not ready.exists() and process.poll() is None:
                time.sleep(0.1)
            if ready.exists():
                _kill(process)
                continue
            process.wait(timeout=15)
            stopped = True
            break
        assert stopped
        with psycopg.connect(DATABASE_URL) as connection:
            row = connection.execute(
                "SELECT goal.status, task.state, workflow.status, count(attempt.id)"
                " FROM panestria.goal AS goal"
                " JOIN panestria.task AS task ON task.goal_id = goal.id"
                " JOIN panestria.task_attempt AS attempt ON attempt.task_id = task.id"
                " JOIN panestria.workflow_link AS link ON link.task_id = task.id"
                " JOIN dbos.workflow_status AS workflow ON workflow.workflow_uuid = link.dbos_workflow_id"
                " WHERE goal.id = %s"
                " GROUP BY goal.status, task.state, workflow.status",
                (submitted,),
            ).fetchone()
        assert row is not None
        assert row[0] != "COMPLETED"
        assert row[1] == "FAILED"
        assert row[2] == "MAX_RECOVERY_ATTEMPTS_EXCEEDED"
        assert int(row[3]) == 1
    finally:
        os.environ.pop("PANESTRIA_DEFER_CONSUME", None)
        subprocess.run([*COMPOSE, "down", "-v"], check=False)
