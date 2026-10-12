"""Loopback TCP process and the real CLI. TestClient is not the sender."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "docs" / "fixtures" / "synthetic-goal-contract.json"
COMPOSE = ["docker", "compose", "-f", str(ROOT / "compose.yaml"), "-p", "panestria-s3"]
DATABASE_URL = "postgresql://panestria_synthetic:placeholder-not-a-secret@127.0.0.1:55432/panestria_synthetic"
TOKEN = "synthetic-loopback-token"
OWNER = "00000000-0000-4000-8000-000000000002"
PROJECT = "00000000-0000-4000-8000-000000000003"
OTHER = "00000000-0000-4000-8000-000000000099"
BASE = "http://127.0.0.1:8766"


def _properties(record_property: pytest.RecordProperty, case_id: str, lane: str = "e2e") -> None:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False)
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, text=True, capture_output=True, check=False)
    record_property("slice_id", "AOS-005-S1")
    record_property("candidate_commit", commit.stdout.strip())
    record_property("fixture_digest", hashlib.sha256(FIXTURE.read_bytes()).hexdigest())
    record_property("lane", lane)
    record_property("execution_mode", "OS_BOUNDARY")
    record_property("worktree_state", "dirty" if dirty.stdout.strip() else "clean")
    record_property("aos_001_tc04", "NOT_RUN")
    record_property("gate_case_id", case_id)


@pytest.fixture(scope="module")
def database() -> None:
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
    yield
    subprocess.run([*COMPOSE, "down", "-v"], check=False)


def _server(sandbox: Path) -> subprocess.Popen[str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("PANESTRIA_")}
    env.update(
        {
            "PANESTRIA_DATABASE_URL": DATABASE_URL,
            "PANESTRIA_TOKEN": TOKEN,
            "PANESTRIA_OWNER_ID": OWNER,
            "PANESTRIA_PROJECT_ID": PROJECT,
            "PANESTRIA_SANDBOX": str(sandbox),
            "PANESTRIA_SCHEMA_VERSION": "1",
            "PANESTRIA_PROFILE": "SYNTHETIC_DEV",
            "PANESTRIA_BIND_HOST": "127.0.0.1",
            "PANESTRIA_BIND_PORT": "8766",
            "PANESTRIA_READINESS_BUDGET_MS": "1000",
        }
    )
    log = (sandbox / "server.log").open("a")
    process = subprocess.Popen(
        [sys.executable, "-m", "panestria.api.serve"],
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    process.log = log  # type: ignore[attr-defined]
    return process


def _live(process: subprocess.Popen[str], sandbox: Path) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError((sandbox / "server.log").read_text())
        try:
            with urllib.request.urlopen(f"{BASE}/healthz", timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.1)
    raise AssertionError("server did not accept loopback connections")


def _stop(process: subprocess.Popen[str]) -> None:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    log = getattr(process, "log", None)
    if log is not None:
        log.close()


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "panestria.cli.main", *args, "--base-url", BASE, "--token", TOKEN],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _json(completed: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert completed.returncode == 0, completed.stderr
    loaded = json.loads(completed.stdout)
    assert isinstance(loaded, dict)
    return loaded


def _contract(goal_id: str, directory: Path) -> Path:
    document = json.loads(FIXTURE.read_text())
    document["goal_id"] = goal_id
    path = directory / f"{goal_id}.json"
    path.write_text(json.dumps(document))
    return path


def _approval(goal_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        listed = _json(_cli("approvals"))
        found = [item for item in listed["approvals"] if isinstance(item, dict) and item.get("goal_id") == goal_id]
        if found:
            return found[0]
        time.sleep(0.2)
    raise AssertionError("approval was not listed")


def test_cli_over_tcp_restarts_and_completes(
    database: None,
    record_property: pytest.RecordProperty,
    tmp_path: Path,
) -> None:
    del database
    _properties(record_property, "AOS-005-TC01")
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    goal_id = "00000000-0000-4000-8000-0000000000c1"
    contract = _contract(goal_id, tmp_path)
    server = _server(sandbox)
    try:
        _live(server, sandbox)
        submitted = _json(_cli("goal", "submit", "--contract", str(contract), "--idempotency-key", "tcp-submit"))
        assert submitted["goal_id"] == goal_id
        assert submitted["replayed"] is False
        consent = _approval(goal_id)
        _stop(server)
        server = _server(sandbox)
        _live(server, sandbox)
        status = _json(_cli("goal", "status", goal_id))
        assert status["status"] == "CREATED"
        events = _json(_cli("goal", "events", goal_id))
        assert any(item.get("kind") == "goal.submitted" for item in events["events"] if isinstance(item, dict))
        restored = _approval(goal_id)
        assert restored["approval_id"] == consent["approval_id"]
        approved = _json(
            _cli(
                "approve",
                str(consent["approval_id"]),
                "--effect-digest",
                str(consent["effect_digest"]),
                "--expected-version",
                str(consent["expected_version"]),
                "--idempotency-key",
                "tcp-consent",
            )
        )
        assert approved["state"] == "APPROVED"
        evidence = _evidence(goal_id)
        shown = _json(_cli("artifact", "show", str(evidence["artifact_id"])))
        assert shown["sha256"] == evidence["artifact_sha256"]
        assert "store" not in json.dumps(shown)
        blob = sandbox / goal_id / "store" / str(evidence["artifact_sha256"])
        original = blob.read_bytes()
        blob.write_bytes(b"tampered")
        denied = _cli("artifact", "show", str(evidence["artifact_id"]))
        assert denied.returncode != 0
        assert json.loads(denied.stderr)["code"] == "corrupt_artifact"
        blob.write_bytes(original)
        foreign = _foreign_artifact()
        hidden = _cli("artifact", "show", foreign)
        assert hidden.returncode != 0
        assert json.loads(hidden.stderr)["code"] == "not_found"
        merge = _approval(goal_id)
        assert merge["approval_id"] != consent["approval_id"]
        _json(
            _cli(
                "approve",
                str(merge["approval_id"]),
                "--effect-digest",
                str(merge["effect_digest"]),
                "--expected-version",
                str(merge["expected_version"]),
                "--idempotency-key",
                "tcp-merge",
            )
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            current = _json(_cli("goal", "status", goal_id))
            if current["status"] == "COMPLETED":
                break
            time.sleep(0.4)
        else:
            raise AssertionError("goal did not complete")
        blocked = _cli("goal", "cancel", goal_id, "--expected-version", "0", "--reason", "too late")
        assert blocked.returncode != 0
        assert json.loads(blocked.stderr)["code"] == "illegal_transition"
    finally:
        _stop(server)


def test_cancel_leaves_prepared_effect_and_git_unchanged(
    database: None, record_property: pytest.RecordProperty, tmp_path: Path
) -> None:
    del database
    _properties(record_property, "AOS-004-TC03")
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    repo = tmp_path / "protected"
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "synthetic@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "synthetic"], check=True)
    (repo / "README.txt").write_text("baseline\n")
    subprocess.run(["git", "-C", str(repo), "add", "README.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "base"], check=True, capture_output=True)
    before = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True, capture_output=True, check=True)
    goal_id = "00000000-0000-4000-8000-0000000000c2"
    server = _server(sandbox)
    try:
        _live(server, sandbox)
        submitted = _cli(
            "goal",
            "submit",
            "--contract",
            str(_contract(goal_id, tmp_path)),
            "--idempotency-key",
            "tcp-cancel",
        )
        _json(submitted)
        _approval(goal_id)
        with psycopg.connect(DATABASE_URL) as connection:
            task = connection.execute("SELECT id::text FROM panestria.task WHERE goal_id = %s", (goal_id,)).fetchone()
            assert task is not None
            connection.execute(
                "INSERT INTO panestria.side_effect"
                " (id, task_id, effect_key, target, request_hash, state)"
                " VALUES (%s, %s, 'merge', 'refs/heads/main', %s, 'PREPARED')",
                (str(uuid4()), task[0], "ab" * 32),
            )
            connection.commit()
        status = _json(_cli("goal", "status", goal_id))
        cancelled = _json(
            _cli(
                "goal",
                "cancel",
                goal_id,
                "--expected-version",
                str(status["task_version"]),
                "--reason",
                "stop before dispatch",
            )
        )
        assert cancelled["task_state"] == "CANCELLING"
        assert cancelled["goal_status"] == "CREATED"
        after = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            text=True,
            capture_output=True,
            check=True,
        )
        assert after.stdout == before.stdout
        with psycopg.connect(DATABASE_URL) as connection:
            effect = connection.execute(
                "SELECT state FROM panestria.side_effect WHERE task_id = %s",
                (task[0],),
            ).fetchone()
            goal = connection.execute("SELECT status FROM panestria.goal WHERE id = %s", (goal_id,)).fetchone()
        assert effect is not None and effect[0] == "PREPARED"
        assert goal is not None and goal[0] == "CREATED"
    finally:
        _stop(server)


def _evidence(goal_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        events = _json(_cli("goal", "events", goal_id))
        recorded = [
            item
            for item in events["events"]
            if isinstance(item, dict) and item.get("kind") == "evidence.recorded"
        ]
        if recorded:
            payload = recorded[-1]["payload"]
            assert isinstance(payload, dict)
            return payload
        time.sleep(0.5)
    raise AssertionError("evidence was not recorded")


def _foreign_artifact() -> str:
    artifact_id = "00000000-0000-4000-8000-0000000000c3"
    goal_id = "00000000-0000-4000-8000-0000000000c4"
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO panestria.principal (id, display_name) VALUES (%s, 'other') ON CONFLICT DO NOTHING",
            (OTHER,),
        )
        connection.execute(
            "INSERT INTO panestria.project (id, owner_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (OTHER, OTHER),
        )
        connection.execute(
            "INSERT INTO panestria.goal (id, owner_id, project_id, intent, status)"
            " VALUES (%s, %s, %s, 'other', 'CREATED')",
            (goal_id, OTHER, OTHER),
        )
        contract_id = str(uuid4())
        connection.execute(
            "INSERT INTO panestria.goal_contract (id, goal_id, version, body, sha256) VALUES (%s, %s, 1, %s, %s)",
            (contract_id, goal_id, '{"autonomy_profile_ref":"synthetic-approve-first-v1"}', "cd" * 32),
        )
        task_id = str(uuid4())
        connection.execute(
            "INSERT INTO panestria.task (id, goal_id, contract_id, name, state)"
            " VALUES (%s, %s, %s, 'other', 'CREATED')",
            (task_id, goal_id, contract_id),
        )
        connection.execute(
            "INSERT INTO panestria.artifact (id, task_id, kind, store_key, sha256, size_bytes)"
            " VALUES (%s, %s, 'candidate', %s, %s, 1)",
            (artifact_id, task_id, "ab" * 32, "ab" * 32),
        )
        connection.commit()
    return artifact_id


def test_server_smoke_records_its_own_loopback_socket(database: None, record_property: pytest.RecordProperty) -> None:
    """Prove the fresh-host measurement against this database. This is not AOS-001-TC04."""
    del database
    _properties(record_property, "AOS-001-TC03")
    spec = importlib.util.spec_from_file_location(
        "panestria_aos_001_measure",
        ROOT / "tests" / "integration" / "test_aos_001.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    listens, egress, rss, startup = module._measure_loopback_smoke()
    assert module.smoke_denial(listens, egress, rss, startup) is None
    assert ("127.0.0.1", 8767) in listens
    assert rss.isdigit() and int(rss) > 0
    assert startup > 0


def test_cli_reports_retryable_error_when_the_api_is_down(
    record_property: pytest.RecordProperty,
) -> None:
    _properties(record_property, "AOS-005-TC04", "chaos")
    held = socket.socket()
    held.bind(("127.0.0.1", 0))
    port = held.getsockname()[1]
    held.close()
    goal_id = "00000000-0000-4000-8000-0000000000c1"
    command = [
        sys.executable,
        "-m",
        "panestria.cli.main",
        "goal",
        "status",
        goal_id,
        "--base-url",
        f"http://127.0.0.1:{port}",
        "--token",
        TOKEN,
    ]
    first = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    second = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    assert first.returncode == 1
    assert second.returncode == 1
    assert first.stdout == ""
    assert second.stdout == ""
    first_body = json.loads(first.stderr)
    second_body = json.loads(second.stderr)
    assert first_body["code"] == "api_unavailable"
    assert first_body["message"] == "api_unavailable"
    assert first_body["retryable"] is True
    assert UUID(str(first_body["correlation_id"])).version == 4
    assert second_body["correlation_id"] != first_body["correlation_id"]
    assert "Traceback" not in first.stderr
    assert f"127.0.0.1:{port}" not in first.stderr
    assert "Connection refused" not in first.stderr
