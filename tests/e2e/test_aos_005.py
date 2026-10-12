"""AOS-005-S1. Loopback goal submit, scoped read, and typed replay.

The completed synthetic journey is AOS-005-TC01 and stays NOT_RUN.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request

import psycopg
import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from panestria.api.auth import GoalApi
from panestria.api.main import create_app
from panestria.cli.goals import read_events, read_status, submit_contract
from panestria.cli.main import app as cli_app
from panestria.config import Settings

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
    application = create_app(
        settings,
        lambda _deadline: None,  # type: ignore[arg-type, return-value]
        GoalApi(TOKEN, OWNER, PROJECT, DATABASE_URL),
    )
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
