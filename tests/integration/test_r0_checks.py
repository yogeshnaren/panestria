"""R0-01 and R0-02. A failed or unbound check cannot authorize completion."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
import pytest

from panestria.execution.synthetic_journey import SyntheticJourney, _evidence_files_match
from panestria.kernel.approvals import ApprovalService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor, GoalService
from panestria.kernel.repositories.approvals import required_verdicts
from panestria.kernel.uow import UnitOfWork

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "docs" / "fixtures" / "synthetic-goal-contract.json"
COMPOSE = ["docker", "compose", "-f", str(ROOT / "compose.yaml"), "-p", "panestria-s3"]
DATABASE_URL = "postgresql://panestria_synthetic:placeholder-not-a-secret@127.0.0.1:55432/panestria_synthetic"
OWNER = "00000000-0000-4000-8000-000000000002"
PROJECT = "00000000-0000-4000-8000-000000000003"
SHA = "ab" * 32
OTHER = "cd" * 32


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


def _stamp(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) + delta).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")


def _seed_task(connection: psycopg.Connection[object], task_id: str, attempt_id: str, check_id: str) -> None:
    goal_id = f"00000000-0000-4000-8000-{task_id[-12:]}"
    contract_id = f"00000000-0000-4000-8000-{check_id[-12:]}"
    connection.execute(
        "INSERT INTO panestria.goal (id, owner_id, project_id, intent, status)"
        " VALUES (%s, %s, %s, 'checks', 'CREATED') ON CONFLICT DO NOTHING",
        (goal_id, OWNER, PROJECT),
    )
    connection.execute(
        "INSERT INTO panestria.goal_contract (id, goal_id, version, body, sha256)"
        " VALUES (%s, %s, 1, %s::jsonb, %s)",
        (contract_id, goal_id, '{"autonomy_profile_ref":"synthetic-approve-first-v1"}', SHA),
    )
    connection.execute(
        "INSERT INTO panestria.task (id, goal_id, contract_id, name, state, lease_epoch)"
        " VALUES (%s, %s, %s, 'check', 'VERIFYING', 0)",
        (task_id, goal_id, contract_id),
    )
    connection.execute(
        "INSERT INTO panestria.task_attempt (id, task_id, attempt_number, lease_epoch, status, adapter)"
        " VALUES (%s, %s, 1, 0, 'SUCCEEDED', 'mock')",
        (attempt_id, task_id),
    )
    connection.execute(
        "INSERT INTO panestria.acceptance_check"
        " (id, contract_id, check_key, description, verifier_type, verifier_spec, required)"
        " VALUES (%s, %s, 'synthetic-required', 'required', 'trusted-command-ref',"
        " '{\"type\":\"trusted-command-ref\"}'::jsonb, true)",
        (check_id, contract_id),
    )


def test_newer_failure_and_unbound_evidence_prepare_no_merge(record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-005-TC02")
    _database()
    try:
        actor = Actor(OWNER, PROJECT)
        service = ApprovalService()
        task_id = "00000000-0000-4000-8000-0000000000a1"
        attempt_id = "00000000-0000-4000-8000-0000000000b1"
        check_id = "00000000-0000-4000-8000-0000000000c1"
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute("INSERT INTO panestria.principal (id, display_name) VALUES (%s, 'owner')", (OWNER,))
            connection.execute("INSERT INTO panestria.project (id, owner_id) VALUES (%s, %s)", (PROJECT, OWNER))
            _seed_task(connection, task_id, attempt_id, check_id)
            connection.execute(
                "INSERT INTO panestria.artifact (id, task_id, attempt_id, kind, store_key, sha256, size_bytes)"
                " VALUES (%s, %s, %s, 'evidence', 'blob', %s, 1)",
                ("00000000-0000-4000-8000-0000000000d1", task_id, attempt_id, SHA),
            )
            connection.execute(
                "INSERT INTO panestria.check_run"
                " (id, acceptance_check_id, attempt_id, task_id, contract_id, verdict,"
                " evidence_artifact_id, candidate_sha256, checked_at)"
                " VALUES (%s, %s, %s, %s,"
                " (SELECT contract_id FROM panestria.task WHERE id = %s),"
                " 'PASS', %s, %s, now() - interval '1 minute')",
                (
                    "00000000-0000-4000-8000-0000000000e1",
                    check_id,
                    attempt_id,
                    task_id,
                    task_id,
                    "00000000-0000-4000-8000-0000000000d1",
                    SHA,
                ),
            )
            connection.commit()
            pending = service.request(
                UnitOfWork(connection),
                actor,
                _preview(task_id, _stamp(timedelta(hours=1))),
            )
            connection.commit()
            decided = service.decide(
                UnitOfWork(connection),
                actor,
                pending.approval_id,
                pending.effect_digest,
                pending.expected_version,
                "approve",
                "approve-once",
            )
            connection.commit()
            connection.execute(
                "INSERT INTO panestria.check_run"
                " (id, acceptance_check_id, attempt_id, task_id, contract_id, verdict, checked_at)"
                " VALUES (%s, %s, %s, %s,"
                " (SELECT contract_id FROM panestria.task WHERE id = %s),"
                " 'FAIL', now())",
                ("00000000-0000-4000-8000-0000000000e2", check_id, attempt_id, task_id, task_id),
            )
            connection.commit()
            verdicts = required_verdicts(UnitOfWork(connection), task_id, SHA)
            assert verdicts == [("synthetic-required", "FAIL")]
            with pytest.raises(KernelDenied) as blocked:
                service.continue_after_approval(
                    UnitOfWork(connection),
                    actor,
                    pending.approval_id,
                    pending.effect_digest,
                    decided.row_version,
                )
            assert blocked.value.code == "unknown_check"
            assert service.effects(UnitOfWork(connection), task_id) == 0

            fresh = "00000000-0000-4000-8000-0000000000a2"
            fresh_attempt = "00000000-0000-4000-8000-0000000000b2"
            fresh_check = "00000000-0000-4000-8000-0000000000c2"
            _seed_task(connection, fresh, fresh_attempt, fresh_check)
            connection.execute(
                "UPDATE panestria.task SET lease_epoch = 1 WHERE id = %s",
                (fresh,),
            )
            connection.execute(
                "INSERT INTO panestria.task_attempt"
                " (id, task_id, attempt_number, lease_epoch, status, adapter)"
                " VALUES (%s, %s, 2, 1, 'RUNNING', 'mock')",
                ("00000000-0000-4000-8000-0000000000b3", fresh),
            )
            connection.execute(
                "INSERT INTO panestria.artifact (id, task_id, attempt_id, kind, store_key, sha256, size_bytes)"
                " VALUES (%s, %s, %s, 'evidence', 'old', %s, 1)",
                ("00000000-0000-4000-8000-0000000000d2", fresh, fresh_attempt, SHA),
            )
            connection.execute(
                "INSERT INTO panestria.check_run"
                " (id, acceptance_check_id, attempt_id, task_id, contract_id, verdict,"
                " evidence_artifact_id, candidate_sha256)"
                " VALUES (%s, %s, %s, %s,"
                " (SELECT contract_id FROM panestria.task WHERE id = %s),"
                " 'PASS', %s, %s)",
                (
                    "00000000-0000-4000-8000-0000000000e3",
                    fresh_check,
                    fresh_attempt,
                    fresh,
                    fresh,
                    "00000000-0000-4000-8000-0000000000d2",
                    SHA,
                ),
            )
            connection.commit()
            assert required_verdicts(UnitOfWork(connection), fresh, SHA) == [("synthetic-required", None)]

            mismatched = "00000000-0000-4000-8000-0000000000a3"
            mismatched_attempt = "00000000-0000-4000-8000-0000000000b4"
            mismatched_check = "00000000-0000-4000-8000-0000000000c3"
            _seed_task(connection, mismatched, mismatched_attempt, mismatched_check)
            connection.execute(
                "INSERT INTO panestria.artifact (id, task_id, attempt_id, kind, store_key, sha256, size_bytes)"
                " VALUES (%s, %s, %s, 'evidence', 'other', %s, 1)",
                ("00000000-0000-4000-8000-0000000000d3", mismatched, mismatched_attempt, OTHER),
            )
            connection.execute(
                "INSERT INTO panestria.check_run"
                " (id, acceptance_check_id, attempt_id, task_id, contract_id, verdict,"
                " evidence_artifact_id, candidate_sha256)"
                " VALUES (%s, %s, %s, %s,"
                " (SELECT contract_id FROM panestria.task WHERE id = %s),"
                " 'PASS', %s, %s)",
                (
                    "00000000-0000-4000-8000-0000000000e4",
                    mismatched_check,
                    mismatched_attempt,
                    mismatched,
                    mismatched,
                    "00000000-0000-4000-8000-0000000000d3",
                    OTHER,
                ),
            )
            connection.commit()
            assert required_verdicts(UnitOfWork(connection), mismatched, SHA) == [("synthetic-required", None)]
    finally:
        subprocess.run([*COMPOSE, "down", "-v"], check=False)


def test_unknown_command_and_narrow_paths_do_not_complete(
    tmp_path: Path, record_property: pytest.RecordProperty
) -> None:
    record_property("gate_case_id", "AOS-004-TC02")
    _database()
    journey = SyntheticJourney()
    actor = Actor(OWNER, PROJECT)
    goals = GoalService()
    approvals = ApprovalService()
    try:
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute("INSERT INTO panestria.principal (id, display_name) VALUES (%s, 'owner')", (OWNER,))
            connection.execute("INSERT INTO panestria.project (id, owner_id) VALUES (%s, %s)", (PROJECT, OWNER))
            connection.commit()
            unknown = _submit(connection, goals, actor, _rewritten("00000000-0000-4000-8000-000000000011", "command"))
            narrow = _submit(connection, goals, actor, _rewritten("00000000-0000-4000-8000-000000000012", "paths"))
        _drive_until_checks(journey, approvals, actor, unknown, tmp_path / "unknown")
        _drive_until_checks(journey, approvals, actor, narrow, tmp_path / "narrow")
        with psycopg.connect(DATABASE_URL) as connection:
            for goal_id in (unknown, narrow):
                goal = connection.execute("SELECT status FROM panestria.goal WHERE id = %s", (goal_id,)).fetchone()
                effect = connection.execute(
                    "SELECT count(*) FROM panestria.side_effect AS effect"
                    " JOIN panestria.task AS task ON task.id = effect.task_id"
                    " WHERE task.goal_id = %s AND effect.state = 'SUCCEEDED'",
                    (goal_id,),
                ).fetchone()
                assert goal is not None and goal[0] != "COMPLETED"
                assert effect is not None and int(effect[0]) == 0
    finally:
        subprocess.run([*COMPOSE, "down", "-v"], check=False)


def _rewritten(goal_id: str, kind: str) -> dict[str, object]:
    document: dict[str, object] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["goal_id"] = goal_id
    acceptance = document["acceptance"]
    assert isinstance(acceptance, list)
    if kind == "command":
        verifier = acceptance[0]["verifier"]
        assert isinstance(verifier, dict)
        verifier["command_ref"] = "not-in-the-command-registry"
        verifier["expected_exit_code"] = 1
    else:
        verifier = acceptance[1]["verifier"]
        assert isinstance(verifier, dict)
        verifier["allowed_paths"] = ["unrelated/**"]
    return document


def _submit(
    connection: psycopg.Connection[object],
    goals: GoalService,
    actor: Actor,
    document: dict[str, object],
) -> str:
    receipt = goals.submit(UnitOfWork(connection), actor, document, str(document["goal_id"]))
    connection.commit()
    return receipt.goal_id


def _drive_until_checks(
    journey: SyntheticJourney,
    approvals: ApprovalService,
    actor: Actor,
    goal_id: str,
    sandbox: Path,
) -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        opened = journey.open_contract_wait(connection, actor, goal_id, sandbox)
        assert opened.approval_id is not None
        decided = approvals.decide(
            UnitOfWork(connection),
            actor,
            opened.approval_id,
            str(opened.effect_digest),
            int(opened.expected_version or 0),
            "approve",
            f"consent-{goal_id[-4:]}",
        )
        connection.commit()
        assert decided.state == "APPROVED"
        finished = journey.resume(connection, actor, goal_id, sandbox)
    assert finished.goal_status != "COMPLETED"
    assert finished.effect_state != "SUCCEEDED"
    assert finished.continuation_kind != "MERGE"


def test_newer_failure_hides_an_older_report_file(
    record_property: pytest.RecordProperty, tmp_path: Path
) -> None:
    record_property("gate_case_id", "AOS-005-TC02")
    _database()
    task_id = "00000000-0000-4000-8000-0000000000a6"
    attempt_id = "00000000-0000-4000-8000-0000000000b6"
    check_id = "00000000-0000-4000-8000-0000000000c6"
    payload = b"older-pass\n"
    digest = hashlib.sha256(payload).hexdigest()
    store = tmp_path / "store"
    store.mkdir()
    (store / digest).write_bytes(payload)
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute("INSERT INTO panestria.principal (id, display_name) VALUES (%s, 'owner')", (OWNER,))
        connection.execute("INSERT INTO panestria.project (id, owner_id) VALUES (%s, %s)", (PROJECT, OWNER))
        _seed_task(connection, task_id, attempt_id, check_id)
        connection.execute(
            "INSERT INTO panestria.artifact (id, task_id, attempt_id, kind, store_key, sha256, size_bytes)"
            " VALUES (%s, %s, %s, 'evidence', 'blob', %s, %s)",
            ("00000000-0000-4000-8000-0000000000d6", task_id, attempt_id, digest, len(payload)),
        )
        connection.execute(
            "INSERT INTO panestria.check_run"
            " (id, acceptance_check_id, attempt_id, task_id, contract_id, verdict,"
            " evidence_artifact_id, candidate_sha256, checked_at)"
            " VALUES (%s, %s, %s, %s,"
            " (SELECT contract_id FROM panestria.task WHERE id = %s),"
            " 'PASS', %s, %s, now() - interval '1 minute')",
            (
                "00000000-0000-4000-8000-0000000000e6",
                check_id,
                attempt_id,
                task_id,
                task_id,
                "00000000-0000-4000-8000-0000000000d6",
                digest,
            ),
        )
        connection.commit()
        assert _evidence_files_match(connection, task_id, store) is True
        connection.execute(
            "INSERT INTO panestria.check_run"
            " (id, acceptance_check_id, attempt_id, task_id, contract_id, verdict, checked_at)"
            " VALUES (%s, %s, %s, %s,"
            " (SELECT contract_id FROM panestria.task WHERE id = %s),"
            " 'FAIL', now())",
            ("00000000-0000-4000-8000-0000000000e7", check_id, attempt_id, task_id, task_id),
        )
        connection.commit()
        assert _evidence_files_match(connection, task_id, store) is False


def _preview(task_id: str, expires_at: str) -> dict[str, object]:
    return {
        "action_kind": "merge",
        "owner_id": OWNER,
        "project_id": PROJECT,
        "task_id": task_id,
        "contract_sha256": SHA,
        "contract_version": 1,
        "policy_version": "synthetic-approve-first-v1",
        "destination": "refs/heads/main",
        "expected_base": "base",
        "candidate_sha256": SHA,
        "required_checks": ["synthetic-required"],
        "minimum_actor_id": OWNER,
        "expires_at": expires_at,
    }
