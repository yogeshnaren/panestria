"""R0-04 and R0-05. A lost Git receipt reconciles; an expired approval does not merge."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import psycopg
import pytest

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
_RESUME = """
import os
from pathlib import Path
import psycopg
from panestria.execution.synthetic_journey import SyntheticJourney
from panestria.kernel.goals import Actor
with psycopg.connect(os.environ["PANESTRIA_DATABASE_URL"]) as connection:
    SyntheticJourney().resume(
        connection,
        Actor(os.environ["PANESTRIA_OWNER"], os.environ["PANESTRIA_PROJECT"]),
        os.environ["PANESTRIA_GOAL_ID"],
        Path(os.environ["PANESTRIA_SANDBOX"]),
    )
"""


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


def _ref(sandbox: Path) -> str:
    completed = subprocess.run(
        ["git", "--git-dir", str(sandbox / "protected" / "dest.git"), "rev-parse", "refs/heads/main"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def _prepare(goal_id: str, sandbox: Path) -> str:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["goal_id"] = goal_id
    actor = Actor(OWNER, PROJECT)
    journey = SyntheticJourney()
    approvals = ApprovalService()
    with psycopg.connect(DATABASE_URL) as connection:
        GoalService().submit(UnitOfWork(connection), actor, document, goal_id)
        connection.commit()
        opened = journey.open_contract_wait(connection, actor, goal_id, sandbox)
        assert opened.approval_id is not None
        approvals.decide(
            UnitOfWork(connection),
            actor,
            opened.approval_id,
            str(opened.effect_digest),
            int(opened.expected_version or 0),
            "approve",
            f"consent-{goal_id[-4:]}",
        )
        connection.commit()
        waiting = journey.resume(connection, actor, goal_id, sandbox)
        assert waiting.continuation_kind == "MERGE"
        assert waiting.approval_id is not None
        approvals.decide(
            UnitOfWork(connection),
            actor,
            waiting.approval_id,
            str(waiting.effect_digest),
            int(waiting.expected_version or 0),
            "approve",
            f"merge-{goal_id[-4:]}",
        )
        connection.commit()
    return _ref(sandbox)


def _spawn(goal_id: str, sandbox: Path, crash_at: str, ready: Path) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env.update(
        {
            "PANESTRIA_DATABASE_URL": DATABASE_URL,
            "PANESTRIA_GOAL_ID": goal_id,
            "PANESTRIA_SANDBOX": str(sandbox),
            "PANESTRIA_OWNER": OWNER,
            "PANESTRIA_PROJECT": PROJECT,
            "PANESTRIA_CRASH_AT": crash_at,
            "PANESTRIA_READY_FILE": str(ready),
        }
    )
    return subprocess.Popen(
        [sys.executable, "-c", _RESUME],
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


def _effect(goal_id: str) -> tuple[str, str, int]:
    with psycopg.connect(DATABASE_URL) as connection:
        row = connection.execute(
            "SELECT goal.status, effect.state, count(attempt.id)"
            " FROM panestria.goal AS goal"
            " JOIN panestria.task AS task ON task.goal_id = goal.id"
            " JOIN panestria.task_attempt AS attempt ON attempt.task_id = task.id"
            " LEFT JOIN panestria.side_effect AS effect ON effect.task_id = task.id"
            " WHERE goal.id = %s"
            " GROUP BY goal.status, effect.state",
            (goal_id,),
        ).fetchone()
    assert row is not None
    return str(row[0]), str(row[1]), int(row[2])


def test_reconcile_applied_ref_and_refuse_stale_authorization(
    tmp_path: Path, record_property: pytest.RecordProperty
) -> None:
    record_property("gate_case_id", "AOS-005-TC04")
    _database()
    try:
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute("INSERT INTO panestria.principal (id, display_name) VALUES (%s, 'owner')", (OWNER,))
            connection.execute("INSERT INTO panestria.project (id, owner_id) VALUES (%s, %s)", (PROJECT, OWNER))
            connection.commit()
        applied = "00000000-0000-4000-8000-000000000021"
        expired = "00000000-0000-4000-8000-000000000022"
        shifted = "00000000-0000-4000-8000-000000000023"
        applied_box = tmp_path / "applied"
        base = _prepare(applied, applied_box)
        crashed = _spawn(applied, applied_box, "before-effect-commit", tmp_path / "applied.ready")
        _wait_ready(tmp_path / "applied.ready", crashed)
        moved = _ref(applied_box)
        assert moved != base
        _kill(crashed)
        assert _effect(applied) == ("CREATED", "PREPARED", 1)
        assert _ref(applied_box) == moved
        with psycopg.connect(DATABASE_URL) as connection:
            SyntheticJourney().resume(connection, Actor(OWNER, PROJECT), applied, applied_box)
        assert _effect(applied) == ("COMPLETED", "SUCCEEDED", 1)
        assert _ref(applied_box) == moved

        expired_box = tmp_path / "expired"
        os.environ["PANESTRIA_APPROVAL_TTL_SECONDS"] = "5"
        expired_base = _prepare(expired, expired_box)
        held = _spawn(expired, expired_box, "before-effect-dispatch", tmp_path / "expired.ready")
        _wait_ready(tmp_path / "expired.ready", held)
        _kill(held)
        assert _ref(expired_box) == expired_base
        time.sleep(6)
        with psycopg.connect(DATABASE_URL) as connection:
            SyntheticJourney().resume(connection, Actor(OWNER, PROJECT), expired, expired_box)
        os.environ.pop("PANESTRIA_APPROVAL_TTL_SECONDS", None)
        assert _ref(expired_box) == expired_base
        goal, state, attempts = _effect(expired)
        assert goal != "COMPLETED"
        assert state != "SUCCEEDED"
        assert attempts == 1

        shifted_box = tmp_path / "shifted"
        shifted_base = _prepare(shifted, shifted_box)
        held_epoch = _spawn(shifted, shifted_box, "before-effect-dispatch", tmp_path / "shifted.ready")
        _wait_ready(tmp_path / "shifted.ready", held_epoch)
        _kill(held_epoch)
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute(
                "UPDATE panestria.task SET lease_epoch = lease_epoch + 1 WHERE goal_id = %s",
                (shifted,),
            )
            connection.commit()
            SyntheticJourney().resume(connection, Actor(OWNER, PROJECT), shifted, shifted_box)
        assert _ref(shifted_box) == shifted_base
        goal, state, attempts = _effect(shifted)
        assert goal != "COMPLETED"
        assert state != "SUCCEEDED"
        assert attempts == 1
    finally:
        os.environ.pop("PANESTRIA_APPROVAL_TTL_SECONDS", None)
        subprocess.run([*COMPOSE, "down", "-v"], check=False)
