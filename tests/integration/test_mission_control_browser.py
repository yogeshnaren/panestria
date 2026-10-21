"""Physical browser/HTTP/PG metadata journey; no provider, model or grant fixtures."""

import json
import os
import select
import signal
import socket
import subprocess
import time
from pathlib import Path

import httpx2 as httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from panestria.api.activity_server import build_activity_app
from panestria.api.mission_web import mount_mission_control
from panestria.cli.main import app as cli
from panestria.config import Settings
from panestria.config_activity import load_activity_settings
from panestria.config_local import LocalApplicationRejected
from panestria.kernel.event_replay import EventReplay
from panestria.kernel.goals import Actor
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.uow import UnitOfWork

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "apps/mission-control/dist"


def configure(f, tmp_path):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    result = CliRunner().invoke(
        cli,
        [
            "activity",
            "init",
            "--directory",
            str(tmp_path / "config"),
            "--owner-id",
            f["owner"],
            "--project-id",
            f["project"],
            "--port",
            str(port),
        ],
    )
    assert result.exit_code == 0, result.output
    path = tmp_path / "config/activity.json"
    config, token = load_activity_settings(path)
    return path, config, token.get_secret_value()


def test_dashboard_namespace_read_only_routes_and_envelope(r1_task, tmp_path):
    _, config, token = configure(r1_task, tmp_path)
    settings = Settings(database_url=r1_task["dsn"]).validate_profile()
    app = build_activity_app(config, settings, token)
    with pytest.raises(LocalApplicationRejected, match="mission_build_required"):
        mount_mission_control(app, config, token, tmp_path / "missing-build")
    mount_mission_control(app, config, token, ASSETS)
    other = build_activity_app(config, settings, token)
    from panestria.api.main import mount_browser_api
    from panestria.api.sessions import BrowserAccess
    from panestria.kernel.sessions import SessionService

    mount_browser_api(
        other, BrowserAccess(config.origin, SessionService(b"synthetic-other-session-32-bytes!!"), r1_task["dsn"])
    )
    try:
        with TestClient(app, base_url=config.origin) as client, TestClient(other, base_url=config.origin) as old:
            assert client.get("/").status_code == 200
            assert "default-src" in client.get("/").headers["content-security-policy"]
            assert client.get("/ui/mission.js").headers["cache-control"] == "no-store"
            assert client.get("/v1/activity").status_code == 401
            bearer = {"Authorization": "Bearer " + token}
            origin = {"Origin": config.origin}
            legacy_code = old.post("/v1/session/code", headers=bearer, json={}).json()["code"]
            assert old.post("/v1/session/pair", headers=origin, json={"code": legacy_code}).status_code == 200
            assert old.get("/v1/activity").status_code == 200
            code = client.post("/v1/session/code", headers=bearer, json={}).json()["code"]
            origin = {"Origin": config.origin}
            assert (
                client.post(
                    "/v1/session/pair", headers={"Origin": "https://evil.invalid"}, json={"code": code}
                ).status_code
                == 403
            )
            # Wrong session purpose cannot consume a challenge or authenticate.
            assert old.post("/v1/session/pair", headers=origin, json={"code": code}).status_code == 401
            pair = client.post("/v1/session/pair", headers=origin, json={"code": code})
            assert pair.status_code == 200
            name = app.state.browser_access.cookie_name
            mission_token = client.cookies.get(name)
            assert old.get("/v1/activity", headers={"Cookie": "panestria_session=" + mission_token}).status_code == 401
            assert old.get("/v1/activity").status_code == 200
            assert client.get("/v1/activity").status_code == 200
            assert client.post("/v1/session/logout", headers=origin, json={}).status_code == 403
            assert client.get("/v1/activity", headers={"Host": "rebind.invalid"}).status_code == 403
            assert client.get("/?token=synthetic").status_code == 400
            for target in ("/v1/goals", "/v1/ask", "/v1/approvals", "/v2/profiles", "/v1/connections"):
                assert client.post(target, headers=bearer, json={}).status_code == 404
            assert (
                client.post(
                    "/v1/session/logout", headers={**origin, "X-Panestria-CSRF": pair.json()["csrf_token"]}, json={}
                ).status_code
                == 200
            )
            assert client.get("/v1/activity").status_code == 401
    finally:
        app.state.health.shutdown()
        other.state.health.shutdown()


def test_actual_chromium_pair_reconnect_large_cursor_resync_and_revoke(r1_migration_task, tmp_path, record_property):
    f = r1_migration_task
    candidate = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    record_property("candidate_commit", candidate)
    record_property(
        "worktree_state",
        "dirty" if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip() else "clean",
    )
    record_property("mode", "ACTUAL_CHROMIUM_POSTGRES_LOOPBACK_HTTP_METADATA_ONLY")
    path, config, token = configure(f, tmp_path)
    with psycopg.connect(f["dsn"]) as c:
        c.execute("ALTER TABLE panestria.task_event ALTER COLUMN seq RESTART WITH 9007199254740993")
        for _ in range(55):
            append_event(
                UnitOfWork(c),
                goal_id=f["goal"],
                task_id=f["task"],
                actor=f["owner"],
                kind="mission.observed",
                payload={"private": "PRIVATE_MISSION_SENTINEL"},
            )
    env = {**os.environ, "PANESTRIA_DATABASE_URL": f["dsn"]}
    server = subprocess.Popen(
        [
            str(ROOT / ".venv/bin/python"),
            "-m",
            "panestria.cli.main",
            "mission-control",
            "serve",
            "--config",
            str(path),
            "--assets",
            str(ASSETS),
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    browser = None
    try:
        with httpx.Client(trust_env=False, timeout=1) as client:
            deadline = time.monotonic() + 10
            while True:
                assert server.poll() is None and time.monotonic() < deadline
                try:
                    if client.get(config.origin + "/").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.05)

        def code():
            result = subprocess.run(
                [
                    str(ROOT / ".venv/bin/python"),
                    "-m",
                    "panestria.cli.main",
                    "mission-control",
                    "pair-code",
                    "--config",
                    str(path),
                ],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert result.returncode == 0 and token not in result.stdout, result.stderr
            return json.loads(result.stdout)["code"]

        fixture = tmp_path / "browser.json"
        fixture.write_text(json.dumps({"origin": config.origin, "goal": f["goal"], "code": code()}))
        fixture.chmod(0o600)
        screenshot = tmp_path / "mission-control.png"
        browser = subprocess.Popen(
            [os.environ.get("PANESTRIA_TEST_NODE", "node"), "tests/journey.mjs"],
            cwd=ROOT / "apps/mission-control",
            env={
                **os.environ,
                "PANESTRIA_BROWSER_FIXTURE": str(fixture),
                "PANESTRIA_BROWSER_SCREENSHOT": str(screenshot),
            },
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert browser.stdout and browser.stdin

        def wait(expected):
            ready, _, _ = select.select([browser.stdout], [], [], 65)
            assert ready, f"browser did not reach {expected}"
            observed = browser.stdout.readline().strip()
            if observed != expected:
                browser.wait(timeout=5)
                raise AssertionError(f"browser expected {expected}, got {observed}: " + browser.stderr.read())

        def advance(body=None):
            browser.stdin.write(json.dumps(body or {"proceed": True}) + "\n")
            browser.stdin.flush()

        wait("OFFLINE")
        with psycopg.connect(f["dsn"]) as c:
            for kind in ("mission.after_disconnect", "goal.completed"):
                append_event(
                    UnitOfWork(c), goal_id=f["goal"], task_id=f["task"], actor=f["owner"], kind=kind, payload={}
                )
            c.execute("UPDATE panestria.task SET state='RECONCILING' WHERE id=%s", (f["task"],))
        advance()
        wait("RETIRE")
        with psycopg.connect(f["dsn"]) as c:
            seq = append_event(
                UnitOfWork(c),
                goal_id=f["goal"],
                task_id=f["task"],
                actor=f["owner"],
                kind="mission.retired",
                payload={},
            )
            EventReplay().retire_before(UnitOfWork(c), Actor(f["owner"], f["project"]), f["goal"], seq, 0)
        advance()
        wait("REVOKE")
        with psycopg.connect(f["dsn"]) as c:
            c.execute("UPDATE panestria.browser_session SET revoked_at=now() WHERE project_id=%s", (f["project"],))
        advance()
        wait("REPAIR")
        advance({"code": code()})
        wait("PASS")
        browser.communicate(timeout=10)
        assert browser.returncode == 0
        assert screenshot.is_file()
        target = os.environ.get("PANESTRIA_MISSION_SCREENSHOT")
        if target:
            import shutil

            shutil.copyfile(screenshot, target)
    finally:
        if browser is not None and browser.poll() is None:
            browser.terminate()
            browser.communicate(timeout=10)
        if server.poll() is None:
            server.send_signal(signal.SIGINT)
        out, err = server.communicate(timeout=10)
        assert server.returncode in {0, 130}, err.decode()
        assert token.encode() not in out + err
