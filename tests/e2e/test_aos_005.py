"""AOS-005 loopback goals and locked approval decisions.

The completed synthetic journey is AOS-005-TC01 and stays NOT_RUN.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
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
from panestria.api.main import create_app, mount_goal_api
from panestria.cli.approvals import decide_approval
from panestria.cli.goals import read_events, read_status, submit_contract
from panestria.cli.main import app as cli_app
from panestria.config import Settings
from panestria.contracts.approval import effect_digest, load_preview
from panestria.kernel.approvals import ApprovalService, ApprovalView
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "docs" / "fixtures" / "synthetic-goal-contract.json"
COMPOSE = ["docker", "compose", "-f", str(ROOT / "compose.yaml"), "-p", "panestria-s3"]
DATABASE_URL = "postgresql://panestria_synthetic:placeholder-not-a-secret@127.0.0.1:55432/panestria_synthetic"
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
            assert status.json() == {"goal_id": first["goal_id"], "status": "CREATED"}
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
            "INSERT INTO panestria.goal_contract (id, goal_id, version, body, sha256) VALUES (%s, %s, 1, '{}', %s)",
            (CONTRACT, GOAL, SHA),
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
            "INSERT INTO panestria.goal_contract (id, goal_id, version, body, sha256) VALUES (%s, %s, 1, '{}', %s)",
            (FOREIGN_CONTRACT, FOREIGN_GOAL, SHA),
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
                "UPDATE panestria.check_run SET verdict = 'PASS', evidence_artifact_id = %s WHERE id = %s",
                ("00000000-0000-4000-8000-000000000091", "00000000-0000-4000-8000-000000000081"),
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
