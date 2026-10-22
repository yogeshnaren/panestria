"""AOS-005 loopback goals and locked approval decisions.

The completed synthetic journey is AOS-005-TC01 and stays NOT_RUN.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request

import psycopg
import pytest
import typer
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from panestria.api.auth import GoalApi
from panestria.api.health import ProbeCheck, ProbeObservation
from panestria.api.main import create_app, mount_goal_api
from panestria.cli.approvals import decide_approval
from panestria.cli.goals import read_events, read_status, submit_contract
from panestria.cli.main import app as cli_app
from panestria.config import Settings
from panestria.contracts.approval import effect_digest, load_preview
from panestria.execution.synthetic_journey import SyntheticJourney
from panestria.kernel.approvals import ApprovalService, ApprovalView
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork
from stack_support import COMPOSE, DATABASE_URL

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "docs" / "fixtures" / "synthetic-goal-contract.json"


TOKEN = "synthetic-loopback-token"
OWNER = "00000000-0000-4000-8000-000000000002"
PROJECT = "00000000-0000-4000-8000-000000000003"


def _properties(record_property: pytest.RecordProperty) -> None:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False)
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, text=True, capture_output=True, check=False)
    record_property("slice_id", "AOS-005-S1")
    record_property("candidate_commit", commit.stdout.strip())
    record_property("fixture_digest", hashlib.sha256(FIXTURE.read_bytes()).hexdigest())
    record_property("lane", "e2e")
    record_property("execution_mode", "OS_BOUNDARY")
    record_property("worktree_state", "dirty" if dirty.stdout.strip() else "clean")
    record_property("aos_005_tc01", "NOT_RUN")


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


def _app() -> TestClient:
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


def _send(client: TestClient):
    def send(request: Request) -> tuple[int, bytes]:
        parts = urlsplit(request.full_url)
        target = parts.path + (f"?{parts.query}" if parts.query else "")
        response = client.request(
            request.get_method(),
            target,
            content=request.data,
            headers={key: value for key, value in request.header_items()},
        )
        return response.status_code, response.content

    return send


def test_loopback_submit_scope_and_replay(record_property: pytest.RecordProperty) -> None:
    _properties(record_property)
    record_property("gate_case_id", "AOS-005-TC01")
    _database()
    try:
        body = FIXTURE.read_bytes()
        document = json.loads(body)
        with _app() as client:
            missing = client.post("/v1/goals", content=body, headers={"Idempotency-Key": "once"})
            assert missing.status_code == 401
            foreign_host = TestClient(client.app, base_url="http://203.0.113.10")
            denied_host = foreign_host.post(
                "/v1/goals",
                content=body,
                headers={"Authorization": f"Bearer {TOKEN}", "Idempotency-Key": "once"},
            )
            assert denied_host.status_code == 403
            assert denied_host.json()["code"] == "invalid_host"
            origin = client.post(
                "/v1/goals",
                content=body,
                headers={
                    "Authorization": f"Bearer {TOKEN}",
                    "Idempotency-Key": "once",
                    "Origin": "http://evil.example",
                },
            )
            assert origin.status_code == 403
            assert origin.json()["code"] == "origin_denied"
            oversized = client.post(
                "/v1/goals",
                content=b"{" + (b"x" * 70000),
                headers={"Authorization": f"Bearer {TOKEN}", "Idempotency-Key": "once"},
            )
            assert oversized.status_code == 413
            created = client.post(
                "/v1/goals",
                content=body,
                headers={"Authorization": f"Bearer {TOKEN}", "Idempotency-Key": "once"},
            )
            assert created.status_code == 202
            first = created.json()
            assert first["replayed"] is False
            assert first["goal_id"] == document["goal_id"]
            replay = client.post(
                "/v1/goals",
                content=body,
                headers={"Authorization": f"Bearer {TOKEN}", "Idempotency-Key": "once"},
            )
            assert replay.status_code == 202
            assert replay.json()["replayed"] is True
            assert replay.json()["contract_sha256"] == first["contract_sha256"]
            changed = json.loads(body)
            changed["intent"] = "a different synthetic intent"
            conflict = client.post(
                "/v1/goals",
                content=json.dumps(changed).encode(),
                headers={"Authorization": f"Bearer {TOKEN}", "Idempotency-Key": "once"},
            )
            assert conflict.status_code == 409
            other = json.loads(body)
            other["owner_id"] = "00000000-0000-4000-8000-000000000099"
            other["goal_id"] = "00000000-0000-4000-8000-0000000000aa"
            hidden = client.post(
                "/v1/goals",
                content=json.dumps(other).encode(),
                headers={"Authorization": f"Bearer {TOKEN}", "Idempotency-Key": "other"},
            )
            assert hidden.status_code == 404
            status = client.get(f"/v1/goals/{first['goal_id']}", headers={"Authorization": f"Bearer {TOKEN}"})
            assert status.status_code == 200
            assert status.json() == {"goal_id": first["goal_id"], "status": "CREATED", "task_version": 0}
            absent = client.get(
                "/v1/goals/00000000-0000-4000-8000-0000000000bb",
                headers={"Authorization": f"Bearer {TOKEN}"},
            )
            assert absent.status_code == 404
            page = client.get(
                f"/v1/goals/{first['goal_id']}/events",
                params={"after": "0"},
                headers={"Authorization": f"Bearer {TOKEN}"},
            )
            assert page.status_code == 200
            assert page.json()["events"][0]["kind"] == "goal.submitted"
            assert page.json()["events"][0]["seq"].isdigit()
            cursor = page.json()["events"][0]["seq"]
            empty = client.get(
                f"/v1/goals/{first['goal_id']}/events",
                params={"after": cursor},
                headers={"Authorization": f"Bearer {TOKEN}"},
            )
            assert empty.json() == {"events": []}
            bad_cursor = client.get(
                f"/v1/goals/{first['goal_id']}/events",
                params={"after": "01"},
                headers={"Authorization": f"Bearer {TOKEN}"},
            )
            assert bad_cursor.status_code == 422
            sender = _send(client)
            cli_status, cli_body = submit_contract(
                base_url="http://127.0.0.1",
                token=TOKEN,
                contract_path=FIXTURE,
                idempotency_key="once",
                send=sender,
            )
            assert cli_status == 202
            assert cli_body["replayed"] is True
            _read_status, view = read_status(
                base_url="http://127.0.0.1",
                token=TOKEN,
                goal_id=str(first["goal_id"]),
                send=sender,
            )
            assert view["status"] == "CREATED"
            _event_status, events = read_events(
                base_url="http://127.0.0.1",
                token=TOKEN,
                goal_id=str(first["goal_id"]),
                after="0",
                send=sender,
            )
            assert events["events"][0]["seq"] == cursor
        runner = CliRunner()
        refused = runner.invoke(
            cli_app,
            [
                "goal",
                "submit",
                "--contract",
                str(FIXTURE),
                "--base-url",
                "http://example.com",
                "--token",
                TOKEN,
                "--idempotency-key",
                "once",
            ],
        )
        assert refused.exit_code == 2
    finally:
        subprocess.run([*COMPOSE, "down", "-v"], check=False)


GOAL = "00000000-0000-4000-8000-0000000000a1"
CONTRACT = "00000000-0000-4000-8000-0000000000a2"
OTHER = "00000000-0000-4000-8000-000000000099"
OTHER_PROJECT = "00000000-0000-4000-8000-000000000098"
SHA = "ab" * 32
MERGE = "00000000-0000-4000-8000-000000000051"
CONSENT = "00000000-0000-4000-8000-000000000052"
DENY = "00000000-0000-4000-8000-000000000053"
EXPIRE = "00000000-0000-4000-8000-000000000054"
ACTOR = "00000000-0000-4000-8000-000000000056"
FOREIGN_GOAL = "00000000-0000-4000-8000-0000000000b1"
FOREIGN_CONTRACT = "00000000-0000-4000-8000-0000000000b2"
FOREIGN_TASK = "00000000-0000-4000-8000-000000000055"
_SERVICE = ApprovalService()


def _stamp(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) + delta).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")


def _preview(task_id: str, action: str, expires: str, minimum_actor: str = OWNER) -> dict[str, Any]:
    return {
        "action_kind": action,
        "owner_id": OWNER,
        "project_id": PROJECT,
        "task_id": task_id,
        "contract_sha256": SHA,
        "contract_version": 1,
        "policy_version": "synthetic-1",
        "destination": "refs/heads/main",
        "expected_base": "base",
        "candidate_sha256": SHA,
        "required_checks": ["synthetic-required"],
        "minimum_actor_id": minimum_actor,
        "expires_at": expires,
    }


def _seed_approvals() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute("INSERT INTO panestria.principal (id, display_name) VALUES (%s, 'other')", (OTHER,))
        connection.execute(
            "INSERT INTO panestria.project (id, owner_id) VALUES (%s, %s)",
            (OTHER_PROJECT, OTHER),
        )
        connection.execute(
            "INSERT INTO panestria.goal (id, owner_id, project_id, intent, status)"
            " VALUES (%s, %s, %s, 'merge', 'CREATED')",
            (GOAL, OWNER, PROJECT),
        )
        connection.execute(
            "INSERT INTO panestria.goal_contract (id, goal_id, version, body, sha256)"
            " VALUES (%s, %s, 1, %s::jsonb, %s)",
            (CONTRACT, GOAL, '{"autonomy_profile_ref":"synthetic-approve-first-v1"}', SHA),
        )
        connection.execute(
            "INSERT INTO panestria.acceptance_check"
            " (id, contract_id, check_key, description, verifier_type, verifier_spec)"
            " VALUES (%s, %s, 'synthetic-required', 'required', 'trusted-command-ref',"
            """ '{"type":"trusted-command-ref"}')""",
            ("00000000-0000-4000-8000-000000000061", CONTRACT),
        )
        for task_id, name, state in (
            (MERGE, "merge", "VERIFYING"),
            (DENY, "deny", "VERIFYING"),
            (EXPIRE, "expire", "VERIFYING"),
            (ACTOR, "actor", "VERIFYING"),
            (CONSENT, "consent", "VALIDATING"),
        ):
            connection.execute(
                "INSERT INTO panestria.task (id, goal_id, contract_id, name, state) VALUES (%s, %s, %s, %s, %s)",
                (task_id, GOAL, CONTRACT, name, state),
            )
        connection.execute(
            "INSERT INTO panestria.task_attempt (id, task_id, attempt_number, lease_epoch, status, adapter)"
            " VALUES (%s, %s, 1, 0, 'SUCCEEDED', 'mock')",
            ("00000000-0000-4000-8000-000000000071", MERGE),
        )
        connection.execute(
            "INSERT INTO panestria.check_run"
            " (id, acceptance_check_id, attempt_id, task_id, contract_id, verdict)"
            " VALUES (%s, %s, %s, %s, %s, 'UNKNOWN')",
            (
                "00000000-0000-4000-8000-000000000081",
                "00000000-0000-4000-8000-000000000061",
                "00000000-0000-4000-8000-000000000071",
                MERGE,
                CONTRACT,
            ),
        )
        connection.execute(
            "INSERT INTO panestria.goal (id, owner_id, project_id, intent, status)"
            " VALUES (%s, %s, %s, 'foreign', 'CREATED')",
            (FOREIGN_GOAL, OTHER, OTHER_PROJECT),
        )
        connection.execute(
            "INSERT INTO panestria.goal_contract (id, goal_id, version, body, sha256)"
            " VALUES (%s, %s, 1, %s::jsonb, %s)",
            (FOREIGN_CONTRACT, FOREIGN_GOAL, '{"autonomy_profile_ref":"synthetic-approve-first-v1"}', SHA),
        )
        connection.execute(
            "INSERT INTO panestria.acceptance_check"
            " (id, contract_id, check_key, description, verifier_type, verifier_spec)"
            " VALUES (%s, %s, 'synthetic-required', 'required', 'trusted-command-ref',"
            """ '{"type":"trusted-command-ref"}')""",
            ("00000000-0000-4000-8000-000000000062", FOREIGN_CONTRACT),
        )
        connection.execute(
            "INSERT INTO panestria.task (id, goal_id, contract_id, name, state)"
            " VALUES (%s, %s, %s, 'foreign', 'VERIFYING')",
            (FOREIGN_TASK, FOREIGN_GOAL, FOREIGN_CONTRACT),
        )
        connection.commit()


def _open(actor: Actor, preview: dict[str, Any]) -> ApprovalView:
    with psycopg.connect(DATABASE_URL) as connection:
        view = _SERVICE.request(UnitOfWork(connection), actor, preview)
        connection.commit()
        return view


def _continue(approval_id: str, digest: str, version: int) -> object:
    with psycopg.connect(DATABASE_URL) as connection:
        try:
            receipt = _SERVICE.continue_after_approval(
                UnitOfWork(connection),
                Actor(OWNER, PROJECT),
                approval_id,
                digest,
                version,
            )
        except KernelDenied:
            connection.rollback()
            raise
        connection.commit()
        return receipt


def _effect_count(task_id: str) -> int:
    with psycopg.connect(DATABASE_URL) as connection:
        row = connection.execute("SELECT count(*) FROM panestria.side_effect WHERE task_id = %s", (task_id,)).fetchone()
    return 0 if row is None else int(row[0])


def test_approval_digest_actor_expiry(record_property: pytest.RecordProperty) -> None:
    """Wrong actor, project, digest, expiry, or an unknown check cannot dispatch."""
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False)
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, text=True, capture_output=True, check=False)
    record_property("gate_case_id", "AOS-005-TC02")
    record_property("candidate_commit", commit.stdout.strip())
    record_property("fixture_digest", hashlib.sha256(FIXTURE.read_bytes()).hexdigest())
    record_property("lane", "security")
    record_property("execution_mode", "OS_BOUNDARY")
    record_property("worktree_state", "dirty" if dirty.stdout.strip() else "clean")
    record_property("aos_005_tc01", "NOT_RUN")
    _database()
    try:
        _seed_approvals()
        later = _stamp(timedelta(hours=1))
        earlier = _stamp(timedelta(hours=-1))
        merge = _open(Actor(OWNER, PROJECT), _preview(MERGE, "merge", later))
        denied = _open(Actor(OWNER, PROJECT), _preview(DENY, "merge", later))
        expired = _open(Actor(OWNER, PROJECT), _preview(EXPIRE, "merge", earlier))
        consent = _open(Actor(OWNER, PROJECT), _preview(CONSENT, "contract_consent", later))
        mismatched_actor = _open(Actor(OWNER, PROJECT), _preview(ACTOR, "merge", later, OTHER))
        foreign_preview = _preview(FOREIGN_TASK, "merge", later, OTHER)
        foreign_preview["owner_id"] = OTHER
        foreign_preview["project_id"] = OTHER_PROJECT
        foreign = _open(Actor(OTHER, OTHER_PROJECT), foreign_preview)
        assert merge.continuation_kind == "MERGE"
        assert consent.continuation_kind == "DISPATCH"
        with _app() as client:
            preview = client.get(f"/v1/approvals/{merge.approval_id}", headers={"Authorization": f"Bearer {TOKEN}"})
            assert preview.status_code == 200
            body = preview.json()
            assert body["effect_digest"] == effect_digest(load_preview(body["preview"]))
            changed = dict(body["preview"])
            changed["candidate_sha256"] = "cd" * 32
            changed_digest = effect_digest(load_preview(changed))
            assert changed_digest != body["effect_digest"]
            mismatch = client.post(
                f"/v1/approvals/{merge.approval_id}/decision",
                json={
                    "decision": "approve",
                    "effect_digest": changed_digest,
                    "expected_version": body["expected_version"],
                },
                headers={"Authorization": f"Bearer {TOKEN}", "Idempotency-Key": "changed"},
            )
            assert mismatch.status_code == 409
            assert mismatch.json()["code"] == "digest_mismatch"
            hidden = client.get(f"/v1/approvals/{foreign.approval_id}", headers={"Authorization": f"Bearer {TOKEN}"})
            assert hidden.status_code == 404
            actor = client.post(
                f"/v1/approvals/{mismatched_actor.approval_id}/decision",
                json={
                    "decision": "approve",
                    "effect_digest": mismatched_actor.effect_digest,
                    "expected_version": mismatched_actor.expected_version,
                },
                headers={"Authorization": f"Bearer {TOKEN}", "Idempotency-Key": "actor"},
            )
            assert actor.status_code == 403
            assert actor.json()["code"] == "actor_mismatch"
            stale = client.post(
                f"/v1/approvals/{expired.approval_id}/decision",
                json={
                    "decision": "approve",
                    "effect_digest": expired.effect_digest,
                    "expected_version": expired.expected_version,
                },
                headers={"Authorization": f"Bearer {TOKEN}", "Idempotency-Key": "expire"},
            )
            assert stale.status_code == 409
            assert stale.json()["code"] == "expired"
            sender = _send(client)
            with pytest.raises(typer.Exit):
                decide_approval(
                    base_url="http://127.0.0.1",
                    token=TOKEN,
                    approval_id=merge.approval_id,
                    effect_digest=changed_digest,
                    expected_version=int(body["expected_version"]),
                    decision="approve",
                    idempotency_key="cli-changed",
                    send=sender,
                )
            approved_status, approved = decide_approval(
                base_url="http://127.0.0.1",
                token=TOKEN,
                approval_id=merge.approval_id,
                effect_digest=str(body["effect_digest"]),
                expected_version=int(body["expected_version"]),
                decision="approve",
                idempotency_key="approve-once",
                send=sender,
            )
            assert approved_status == 200
            assert approved["state"] == "APPROVED"
            assert approved["effect_digest"] == body["effect_digest"]
            assert approved["replayed"] is False
            replay_status, replay = decide_approval(
                base_url="http://127.0.0.1",
                token=TOKEN,
                approval_id=merge.approval_id,
                effect_digest=str(body["effect_digest"]),
                expected_version=int(body["expected_version"]),
                decision="approve",
                idempotency_key="approve-once",
                send=sender,
            )
            assert replay_status == 200
            assert replay["replayed"] is True
            with pytest.raises(typer.Exit):
                decide_approval(
                    base_url="http://127.0.0.1",
                    token=TOKEN,
                    approval_id=merge.approval_id,
                    effect_digest=str(body["effect_digest"]),
                    expected_version=int(approved["row_version"]),
                    decision="deny",
                    idempotency_key="approve-once",
                    send=sender,
                )
            deny_status, deny_body = decide_approval(
                base_url="http://127.0.0.1",
                token=TOKEN,
                approval_id=denied.approval_id,
                effect_digest=denied.effect_digest,
                expected_version=denied.expected_version,
                decision="deny",
                idempotency_key="deny-once",
                send=sender,
            )
            assert deny_status == 200
            assert deny_body["state"] == "DENIED"
            consent_status, consent_body = decide_approval(
                base_url="http://127.0.0.1",
                token=TOKEN,
                approval_id=consent.approval_id,
                effect_digest=consent.effect_digest,
                expected_version=consent.expected_version,
                decision="approve",
                idempotency_key="consent-once",
                send=sender,
            )
            assert consent_status == 200
        assert _effect_count(MERGE) == 0
        with pytest.raises(KernelDenied) as unknown:
            _continue(merge.approval_id, merge.effect_digest, int(approved["row_version"]))
        assert unknown.value.code == "unknown_check"
        assert _effect_count(MERGE) == 0
        with psycopg.connect(DATABASE_URL) as connection:
            goal = connection.execute("SELECT status FROM panestria.goal WHERE id = %s", (GOAL,)).fetchone()
            task = connection.execute("SELECT state FROM panestria.task WHERE id = %s", (MERGE,)).fetchone()
            assert goal is not None and goal[0] != "COMPLETED"
            assert task is not None and task[0] == "WAITING_APPROVAL"
            connection.execute(
                "INSERT INTO panestria.artifact (id, task_id, attempt_id, kind, store_key, sha256, size_bytes)"
                " VALUES (%s, %s, %s, 'evidence', 'blob', %s, 1)",
                ("00000000-0000-4000-8000-000000000091", MERGE, "00000000-0000-4000-8000-000000000071", SHA),
            )
            connection.execute(
                "UPDATE panestria.check_run"
                " SET verdict = 'PASS', evidence_artifact_id = %s, candidate_sha256 = %s WHERE id = %s",
                ("00000000-0000-4000-8000-000000000091", SHA, "00000000-0000-4000-8000-000000000081"),
            )
            connection.commit()
        continued = _continue(merge.approval_id, merge.effect_digest, int(approved["row_version"]))
        assert continued.task_state == "VERIFYING"  # type: ignore[attr-defined]
        assert continued.effect_id is not None  # type: ignore[attr-defined]
        assert _effect_count(MERGE) == 1
        again = _continue(merge.approval_id, merge.effect_digest, int(approved["row_version"]))
        assert again.replayed is True  # type: ignore[attr-defined]
        assert again.effect_id == continued.effect_id  # type: ignore[attr-defined]
        with psycopg.connect(DATABASE_URL) as connection:
            attempts = connection.execute(
                "SELECT count(*) FROM panestria.task_attempt WHERE task_id = %s",
                (MERGE,),
            ).fetchone()
            assert attempts is not None and int(attempts[0]) == 1
        with pytest.raises(KernelDenied) as denied_effect:
            _continue(denied.approval_id, denied.effect_digest, int(deny_body["row_version"]))
        assert denied_effect.value.code == "not_approved"
        with pytest.raises(KernelDenied) as expired_effect:
            _continue(expired.approval_id, expired.effect_digest, expired.expected_version + 1)
        assert expired_effect.value.code == "expired"
        assert _effect_count(DENY) == 0
        assert _effect_count(EXPIRE) == 0
        resumed = _continue(consent.approval_id, consent.effect_digest, int(consent_body["row_version"]))
        assert resumed.task_state == "READY"  # type: ignore[attr-defined]
        assert resumed.effect_id is None  # type: ignore[attr-defined]
        assert _effect_count(CONSENT) == 0
        refused = CliRunner().invoke(
            cli_app,
            [
                "approve",
                merge.approval_id,
                "--effect-digest",
                SHA,
                "--expected-version",
                "1",
                "--idempotency-key",
                "x",
                "--base-url",
                "http://example.com",
                "--token",
                TOKEN,
            ],
        )
        assert refused.exit_code == 2
    finally:
        subprocess.run([*COMPOSE, "down", "-v"], check=False)


def _case(record_property: pytest.RecordProperty, case_id: str, lane: str) -> None:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False)
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, text=True, capture_output=True, check=False)
    record_property("gate_case_id", case_id)
    record_property("candidate_commit", commit.stdout.strip())
    record_property("fixture_digest", hashlib.sha256(FIXTURE.read_bytes()).hexdigest())
    record_property("lane", lane)
    record_property("execution_mode", "OS_BOUNDARY")
    record_property("worktree_state", "dirty" if dirty.stdout.strip() else "clean")


def test_r0_positive_journey(record_property: pytest.RecordProperty, tmp_path: Path) -> None:
    """Consent, one mock candidate, independent evidence, and one confirmed effect complete the goal."""
    _case(record_property, "AOS-005-TC01", "e2e")
    _database()
    journey = SyntheticJourney()
    sandbox = tmp_path / "sandbox"
    try:
        with _app() as client:
            sender = _send(client)
            status, submitted = submit_contract(
                base_url="http://127.0.0.1",
                token=TOKEN,
                contract_path=FIXTURE,
                idempotency_key="journey",
                send=sender,
            )
            assert status == 202
            goal_id = str(submitted["goal_id"])
            with psycopg.connect(DATABASE_URL) as connection:
                opened = journey.open_contract_wait(connection, Actor(OWNER, PROJECT), goal_id, sandbox)
            assert opened.attempts == 0
            assert opened.continuation_kind == "DISPATCH"
            assert opened.approval_id is not None
            approved_status, approved = decide_approval(
                base_url="http://127.0.0.1",
                token=TOKEN,
                approval_id=opened.approval_id,
                effect_digest=str(opened.effect_digest),
                expected_version=int(opened.expected_version or 0),
                decision="approve",
                idempotency_key="consent",
                send=sender,
            )
            assert approved_status == 200
            assert approved["state"] == "APPROVED"
            with psycopg.connect(DATABASE_URL) as connection:
                waiting = journey.resume(connection, Actor(OWNER, PROJECT), goal_id, sandbox)
            assert waiting.attempts == 1
            assert waiting.continuation_kind == "MERGE"
            assert waiting.artifact_sha256
            _event_status, events = read_events(
                base_url="http://127.0.0.1",
                token=TOKEN,
                goal_id=goal_id,
                after="0",
                send=sender,
            )
            recorded = [item for item in events["events"] if item["kind"] == "evidence.recorded"]
            assert recorded[0]["payload"]["artifact_sha256"] == waiting.artifact_sha256
            assert recorded[0]["payload"]["verdict"] == "PASS"
            merge_status, merge = decide_approval(
                base_url="http://127.0.0.1",
                token=TOKEN,
                approval_id=str(waiting.approval_id),
                effect_digest=str(waiting.effect_digest),
                expected_version=int(waiting.expected_version or 0),
                decision="approve",
                idempotency_key="merge",
                send=sender,
            )
            assert merge_status == 200
            assert merge["state"] == "APPROVED"
            with psycopg.connect(DATABASE_URL) as connection:
                done = journey.resume(connection, Actor(OWNER, PROJECT), goal_id, sandbox)
            assert done.goal_status == "COMPLETED"
            assert done.task_state == "COMPLETED"
            assert done.effect_state == "SUCCEEDED"
            assert done.attempts == 1
            _status, view = read_status(base_url="http://127.0.0.1", token=TOKEN, goal_id=goal_id, send=sender)
            assert view["status"] == "COMPLETED"
    finally:
        subprocess.run([*COMPOSE, "down", "-v"], check=False)


def test_corrupted_check_report_prepares_no_merge(record_property: pytest.RecordProperty, tmp_path: Path) -> None:
    """A rewritten report file cannot prepare or execute the merge."""
    _case(record_property, "AOS-005-TC02", "security")
    _database()
    journey = SyntheticJourney()
    sandbox = tmp_path / "sandbox"
    try:
        with _app() as client:
            sender = _send(client)
            status, submitted = submit_contract(
                base_url="http://127.0.0.1",
                token=TOKEN,
                contract_path=FIXTURE,
                idempotency_key="corrupt-report",
                send=sender,
            )
            assert status == 202
            goal_id = str(submitted["goal_id"])
            with psycopg.connect(DATABASE_URL) as connection:
                opened = journey.open_contract_wait(connection, Actor(OWNER, PROJECT), goal_id, sandbox)
            _approve(
                sender,
                opened.approval_id,
                str(opened.effect_digest),
                int(opened.expected_version or 0),
                "consent",
            )
            with psycopg.connect(DATABASE_URL) as connection:
                waiting = journey.resume(connection, Actor(OWNER, PROJECT), goal_id, sandbox)
            assert waiting.continuation_kind == "MERGE"
            protected = sandbox / "protected" / "dest.git"
            before = subprocess.run(
                ["git", "--git-dir", str(protected), "rev-parse", "refs/heads/main"],
                text=True,
                capture_output=True,
                check=True,
            )
            with psycopg.connect(DATABASE_URL) as connection:
                rows = connection.execute(
                    "SELECT artifact.sha256 FROM panestria.artifact AS artifact"
                    " JOIN panestria.task AS task ON task.id = artifact.task_id"
                    " WHERE task.goal_id = %s AND artifact.kind = 'check-report'",
                    (goal_id,),
                ).fetchall()
            assert rows
            for (digest,) in rows:
                path = sandbox / "store" / str(digest).strip()
                assert path.is_file()
                path.write_bytes(b"corrupted-report")
            _approve(
                sender,
                str(waiting.approval_id),
                str(waiting.effect_digest),
                int(waiting.expected_version or 0),
                "merge",
            )
            with psycopg.connect(DATABASE_URL) as connection:
                done = journey.resume(connection, Actor(OWNER, PROJECT), goal_id, sandbox)
                effects = connection.execute(
                    "SELECT count(*) FROM panestria.side_effect AS effect"
                    " JOIN panestria.task AS task ON task.id = effect.task_id"
                    " WHERE task.goal_id = %s",
                    (goal_id,),
                ).fetchone()
            assert done.goal_status != "COMPLETED"
            assert done.effect_state != "SUCCEEDED"
            assert effects is not None and int(effects[0]) == 0
            after = subprocess.run(
                ["git", "--git-dir", str(protected), "rev-parse", "refs/heads/main"],
                text=True,
                capture_output=True,
                check=True,
            )
            assert after.stdout == before.stdout
    finally:
        subprocess.run([*COMPOSE, "down", "-v"], check=False)


def _approve(sender: Any, approval_id: str | None, digest: str, version: int, key: str) -> None:
    assert approval_id is not None
    status, body = decide_approval(
        base_url="http://127.0.0.1",
        token=TOKEN,
        approval_id=approval_id,
        effect_digest=digest,
        expected_version=version,
        decision="approve",
        idempotency_key=key,
        send=sender,
    )
    assert status == 200
    assert body["state"] == "APPROVED"


def test_decision_race_idempotency(record_property: pytest.RecordProperty) -> None:
    """One racing decision and one racing consume survive. A changed repeat conflicts."""
    _case(record_property, "AOS-005-TC03", "integration")
    _database()
    try:
        _seed_approvals()
        later = _stamp(timedelta(hours=1))
        service = ApprovalService()
        actor = Actor(OWNER, PROJECT)
        with psycopg.connect(DATABASE_URL) as connection:
            pending = service.request(connection, actor, _preview(DENY, "merge", later))
            ready = service.request(connection, actor, _preview(MERGE, "merge", later))
            connection.commit()
        with psycopg.connect(DATABASE_URL) as connection:
            service.decide(
                UnitOfWork(connection),
                actor,
                ready.approval_id,
                ready.effect_digest,
                ready.expected_version,
                "approve",
                "ready-once",
            )
            connection.commit()
        barrier = threading.Barrier(2)
        raced: list[str] = ["", ""]

        def decide(index: int, decision: str, key: str) -> None:
            barrier.wait(5)
            with psycopg.connect(DATABASE_URL) as connection:
                try:
                    receipt = service.decide(
                        UnitOfWork(connection),
                        actor,
                        pending.approval_id,
                        pending.effect_digest,
                        pending.expected_version,
                        decision,
                        key,
                    )
                    connection.commit()
                    raced[index] = receipt.state
                except KernelDenied as exc:
                    connection.rollback()
                    raced[index] = exc.code

        threads = [
            threading.Thread(target=decide, args=(0, "approve", "race-approve")),
            threading.Thread(target=decide, args=(1, "deny", "race-deny")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        assert sorted(raced) in (["APPROVED", "decision_conflict"], ["DENIED", "decision_conflict"])
        with psycopg.connect(DATABASE_URL) as connection:
            state = connection.execute(
                "SELECT state FROM panestria.approval_request WHERE id = %s",
                (pending.approval_id,),
            ).fetchone()
            events = connection.execute(
                "SELECT count(*) FROM panestria.task_event WHERE kind = 'approval.decided' AND task_id = %s",
                (DENY,),
            ).fetchone()
            assert state is not None and state[0] in {"APPROVED", "DENIED"}
            assert events is not None and int(events[0]) == 1
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute(
                "INSERT INTO panestria.artifact (id, task_id, attempt_id, kind, store_key, sha256, size_bytes)"
                " VALUES (%s, %s, %s, 'evidence', 'blob', %s, 1)",
                ("00000000-0000-4000-8000-000000000091", MERGE, "00000000-0000-4000-8000-000000000071", SHA),
            )
            connection.execute(
                "UPDATE panestria.check_run"
                " SET verdict = 'PASS', evidence_artifact_id = %s, candidate_sha256 = %s WHERE task_id = %s",
                ("00000000-0000-4000-8000-000000000091", SHA, MERGE),
            )
            version = connection.execute("SELECT row_version FROM panestria.task WHERE id = %s", (MERGE,)).fetchone()
            connection.commit()
        assert version is not None
        consumed: list[str] = ["", ""]

        def consume(index: int) -> None:
            barrier2.wait(5)
            with psycopg.connect(DATABASE_URL) as connection:
                try:
                    receipt = service.continue_after_approval(
                        UnitOfWork(connection),
                        actor,
                        ready.approval_id,
                        ready.effect_digest,
                        int(version[0]),
                    )
                    connection.commit()
                    consumed[index] = receipt.effect_id or "none"
                except KernelDenied as exc:
                    connection.rollback()
                    consumed[index] = exc.code

        barrier2 = threading.Barrier(2)
        workers = [threading.Thread(target=consume, args=(0,)), threading.Thread(target=consume, args=(1,))]
        for thread in workers:
            thread.start()
        for thread in workers:
            thread.join(10)
        assert _effect_count(MERGE) == 1
        assert len({item for item in consumed if item not in {"", "not_approved", "version_conflict"}}) == 1
        with psycopg.connect(DATABASE_URL) as connection:
            other = service.request(connection, actor, _preview(EXPIRE, "merge", later))
            service.decide(
                UnitOfWork(connection),
                actor,
                other.approval_id,
                other.effect_digest,
                other.expected_version,
                "approve",
                "same-body",
            )
            connection.commit()
        with psycopg.connect(DATABASE_URL) as connection:
            try:
                service.decide(
                    UnitOfWork(connection),
                    actor,
                    other.approval_id,
                    other.effect_digest,
                    other.expected_version,
                    "deny",
                    "same-body",
                )
                connection.commit()
                changed = "committed"
            except KernelDenied as exc:
                connection.rollback()
                changed = exc.code
        assert changed == "idempotency_conflict"
    finally:
        subprocess.run([*COMPOSE, "down", "-v"], check=False)


def _copy_contract(path: Path, goal_id: str) -> Path:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["goal_id"] = goal_id
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_wait_restart_continuation(record_property: pytest.RecordProperty, tmp_path: Path) -> None:
    """A contract wait does not dispatch, and a merge wait does not launch another worker."""
    _case(record_property, "AOS-005-TC04", "chaos")
    _database()
    journey = SyntheticJourney()
    sandbox = tmp_path / "restart"
    try:
        with _app() as client:
            sender = _send(client)
            _status, submitted = submit_contract(
                base_url="http://127.0.0.1",
                token=TOKEN,
                contract_path=FIXTURE,
                idempotency_key="restart",
                send=sender,
            )
            goal_id = str(submitted["goal_id"])
            actor = Actor(OWNER, PROJECT)
            with psycopg.connect(DATABASE_URL) as connection:
                opened = journey.open_contract_wait(connection, actor, goal_id, sandbox)
                held = journey.resume(connection, actor, goal_id, sandbox)
            assert held.attempts == 0
            assert held.task_state == "WAITING_APPROVAL"
            assert held.continuation_kind == "DISPATCH"
            decide_approval(
                base_url="http://127.0.0.1",
                token=TOKEN,
                approval_id=str(opened.approval_id),
                effect_digest=str(opened.effect_digest),
                expected_version=int(opened.expected_version or 0),
                decision="approve",
                idempotency_key="restart-consent",
                send=sender,
            )
            with psycopg.connect(DATABASE_URL) as connection:
                waiting = journey.resume(connection, actor, goal_id, sandbox)
                again = journey.resume(connection, actor, goal_id, sandbox)
            assert waiting.attempts == 1
            assert again.attempts == 1
            assert again.task_state == "WAITING_APPROVAL"
            assert again.continuation_kind == "MERGE"
            assert again.goal_status != "COMPLETED"
            decide_approval(
                base_url="http://127.0.0.1",
                token=TOKEN,
                approval_id=str(again.approval_id),
                effect_digest=str(again.effect_digest),
                expected_version=int(again.expected_version or 0),
                decision="approve",
                idempotency_key="restart-merge",
                send=sender,
            )
            with psycopg.connect(DATABASE_URL) as connection:
                done = journey.resume(connection, actor, goal_id, sandbox)
            assert done.attempts == 1
            assert done.goal_status == "COMPLETED"
            assert done.effect_state == "SUCCEEDED"
            stale_id = "00000000-0000-4000-8000-0000000000c1"
            stale_box = tmp_path / "stale"
            _copy_contract(tmp_path / "stale.json", stale_id)
            _status, stale_goal = submit_contract(
                base_url="http://127.0.0.1",
                token=TOKEN,
                contract_path=tmp_path / "stale.json",
                idempotency_key="stale",
                send=sender,
            )
            with psycopg.connect(DATABASE_URL) as connection:
                stale_open = journey.open_contract_wait(connection, actor, str(stale_goal["goal_id"]), stale_box)
            decide_approval(
                base_url="http://127.0.0.1",
                token=TOKEN,
                approval_id=str(stale_open.approval_id),
                effect_digest=str(stale_open.effect_digest),
                expected_version=int(stale_open.expected_version or 0),
                decision="approve",
                idempotency_key="stale-consent",
                send=sender,
            )
            with psycopg.connect(DATABASE_URL) as connection:
                stale_wait = journey.resume(connection, actor, str(stale_goal["goal_id"]), stale_box)
            moved = subprocess.run(
                ["git", "-C", str(stale_box / "repo"), "commit", "--allow-empty", "-m", "stale"],
                text=True,
                capture_output=True,
                check=False,
            )
            assert moved.returncode == 0, moved.stderr
            fetched = subprocess.run(
                [
                    "git",
                    "--git-dir",
                    str(stale_box / "protected" / "dest.git"),
                    "fetch",
                    str(stale_box / "repo"),
                    "HEAD:refs/heads/main",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            assert fetched.returncode == 0, fetched.stderr
            decide_approval(
                base_url="http://127.0.0.1",
                token=TOKEN,
                approval_id=str(stale_wait.approval_id),
                effect_digest=str(stale_wait.effect_digest),
                expected_version=int(stale_wait.expected_version or 0),
                decision="approve",
                idempotency_key="stale-merge",
                send=sender,
            )
            with psycopg.connect(DATABASE_URL) as connection:
                rejected = journey.resume(connection, actor, str(stale_goal["goal_id"]), stale_box)
            assert rejected.attempts == 1
            assert rejected.goal_status != "COMPLETED"
            assert rejected.effect_state == "FAILED"
            denied_id = "00000000-0000-4000-8000-0000000000c2"
            _copy_contract(tmp_path / "deny.json", denied_id)
            _status, denied_goal = submit_contract(
                base_url="http://127.0.0.1",
                token=TOKEN,
                contract_path=tmp_path / "deny.json",
                idempotency_key="deny-goal",
                send=sender,
            )
            with psycopg.connect(DATABASE_URL) as connection:
                denied_open = journey.open_contract_wait(
                    connection,
                    actor,
                    str(denied_goal["goal_id"]),
                    tmp_path / "deny-box",
                )
            decide_approval(
                base_url="http://127.0.0.1",
                token=TOKEN,
                approval_id=str(denied_open.approval_id),
                effect_digest=str(denied_open.effect_digest),
                expected_version=int(denied_open.expected_version or 0),
                decision="deny",
                idempotency_key="deny-consent",
                send=sender,
            )
            with psycopg.connect(DATABASE_URL) as connection:
                denied = journey.resume(connection, actor, str(denied_goal["goal_id"]), tmp_path / "deny-box")
                again = journey.resume(connection, actor, str(denied_goal["goal_id"]), tmp_path / "deny-box")
            assert denied.attempts == 0
            assert denied.goal_status == "CANCELLED"
            assert denied.task_state == "CANCELLED"
            assert again.goal_status == "CANCELLED"
            assert again.attempts == 0
    finally:
        subprocess.run([*COMPOSE, "down", "-v"], check=False)


_REQUIRED_ROUTES = {
    "/healthz",
    "/readyz",
    "/v1/approvals",
    "/v1/approvals/{approval_id}/decision",
    "/v1/artifacts/{artifact_id}",
    "/v1/goals",
    "/v1/goals/{goal_id}",
    "/v1/goals/{goal_id}/cancel",
    "/v1/goals/{goal_id}/events",
}


def _openapi_document() -> dict[str, Any]:
    def probe(deadline: datetime) -> ProbeObservation:
        del deadline
        return ProbeObservation(checks=[ProbeCheck(name="database", status="unavailable", reason="not_probed")])

    settings = Settings.model_validate(
        {
            "schema_version": 1,
            "profile": "SYNTHETIC_DEV",
            "bind_host": "127.0.0.1",
            "bind_port": 8765,
            "readiness_budget_ms": 500,
            "database_url": DATABASE_URL,
        }
    )
    app = create_app(settings, probe)
    try:
        mount_goal_api(app, GoalApi(TOKEN, OWNER, PROJECT, DATABASE_URL))
        # Optional local mode's actual registered routes, for the shared typed
        # catalog only. No provider is instantiated and no service is enabled.
        from panestria.api.routes.ask import router as ask_router

        app.include_router(ask_router)
        from panestria.api.routes.research_intake import router as research_intake_router

        app.include_router(research_intake_router)
        from panestria.api.routes.build_intake import router as build_intake_router

        app.include_router(build_intake_router)
        document = app.openapi()
    finally:
        app.state.health.shutdown()
    if not isinstance(document, dict):
        raise AssertionError("openapi document is not an object")
    return document


def test_openapi_matches_the_mounted_routes(record_property: pytest.RecordProperty) -> None:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False)
    record_property("gate_case_id", "AOS-005-TC01")
    record_property("candidate_commit", commit.stdout.strip())
    record_property("lane", "contract")
    record_property("execution_mode", "HERMETIC")
    document = _openapi_document()
    text = json.dumps(document, indent=2, sort_keys=True) + "\n"
    assert text == (ROOT / "docs" / "api" / "openapi.json").read_text(encoding="utf-8")
    paths = document.get("paths")
    assert isinstance(paths, dict)
    assert _REQUIRED_ROUTES <= set(paths)
    assert "placeholder-not-a-secret" not in text
    assert TOKEN not in text
    assert "GoalStatus" in text


def test_cli_rejects_a_status_body_outside_the_published_model(record_property: pytest.RecordProperty) -> None:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False)
    record_property("gate_case_id", "AOS-005-TC01")
    record_property("candidate_commit", commit.stdout.strip())
    record_property("lane", "contract")
    record_property("execution_mode", "HERMETIC")
    body = {
        "goal_id": "00000000-0000-4000-8000-000000000001",
        "status": "COMPLETED",
        "task_version": 11,
    }
    accepted = read_status(
        base_url="http://127.0.0.1:9",
        token=TOKEN,
        goal_id=body["goal_id"],
        send=lambda _request: (200, json.dumps(body).encode()),
    )
    assert accepted[1]["status"] == "COMPLETED"
    with pytest.raises(typer.Exit):
        read_status(
            base_url="http://127.0.0.1:9",
            token=TOKEN,
            goal_id=body["goal_id"],
            send=lambda _request: (200, b'{"goal_id": "x", "status": "COMPLETED"}'),
        )
