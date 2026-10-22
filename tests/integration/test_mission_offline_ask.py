"""Physical browser/HTTP/Postgres; model, process and hardware are explicit fixtures."""

import asyncio
import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

import httpx2 as httpx
import psycopg
import pytest
import uvicorn
from fastapi.testclient import TestClient
from test_local_server import ModelFixture, configuration

from panestria.api import local_server
from panestria.api.local_protocol import LocalHttpProtocol
from panestria.api.mission_web import mount_mission_control
from panestria.config import Settings
from panestria.config_activity import ActivitySettings
from panestria.config_local import LocalApplicationRejected, load_local_settings
from panestria.inference.runtime import MODEL, MODEL_DIGEST
from panestria.kernel.local_setup import LocalSetupIntent, LocalSetupService
from panestria.kernel.uow import UnitOfWork
from panestria.resources.hardware import HardwareProbe

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "apps/mission-control/dist"
ANSWER = '<img src=x onerror="window.askInjected=true"><script>window.askInjected=true</script> READY'


@pytest.fixture
def ask_application(r1_database, tmp_path, monkeypatch):
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    path, _ = configuration(tmp_path, port=port)
    config, token = load_local_settings(path)
    with psycopg.connect(r1_database) as db:
        LocalSetupService().initialize(
            UnitOfWork(db),
            LocalSetupIntent(owner_id=config.owner_id, project_id=config.project_id, intent="OFFLINE_ASK"),
        )
    monkeypatch.setattr(local_server, "ModelRuntime", ModelFixture)
    archive = ROOT / "docs/specification/attachments/agentos-skills-v0.1.0.zip"
    manifest = HardwareProbe(archive).collect(preset="omen-8gb")
    monkeypatch.setattr(local_server.HardwareProbe, "collect_cpu", lambda self: manifest)
    settings = Settings(database_url=r1_database).validate_profile()
    app = local_server.build_local_app(config, settings, token.get_secret_value(), mission_assets=ASSETS)
    calls = []

    async def model_fixture(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": MODEL, "digest": MODEL_DIGEST}]})
        assert request.url.path == "/api/generate"
        body = json.loads(request.content)
        calls.append(body)
        if "WAIT_FOR_CANCEL" in body["prompt"]:
            await asyncio.sleep(120)  # cancelled by the real Ask controller, never awaited to completion
            raise AssertionError("controller did not cancel")
        if "MODEL_UNAVAILABLE" in body["prompt"]:
            return httpx.Response(503)
        frames = [
            {"model": MODEL, "response": ANSWER, "done": False},
            {
                "model": MODEL,
                "response": "",
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 12,
                "eval_count": 2,
            },
        ]
        return httpx.Response(200, content="\n".join(json.dumps(f) for f in frames))

    app.state.ask_api.provider.transport = httpx.MockTransport(model_fixture)
    yield path, config, token.get_secret_value(), settings, app, calls
    app.state.health.shutdown()


def test_mission_ask_scope_and_session_purpose(ask_application):
    _, config, token, settings, app, calls = ask_application
    original = local_server.build_local_app(
        config.model_copy(update={"runtime_directory": config.runtime_directory / "legacy"}), settings, token
    )
    origin = {"Origin": config.origin}
    bearer = {"Authorization": "Bearer " + token}
    with TestClient(original, base_url=config.origin) as old:
        assert 'id="question"' in old.get("/").text
        old_code = old.post("/v1/session/code", headers=bearer, json={}).json()["code"]
        old.post("/v1/session/pair", headers=origin, json={"code": old_code}).raise_for_status()
        cookies = dict(old.cookies)
    with TestClient(app, base_url=config.origin) as client:
        assert client.get("/v1/mission/capabilities").status_code == 401
        assert client.get("/ui/mission.js").headers["cache-control"] == "no-store"
        assert "script-src 'self'" in client.get("/").headers["content-security-policy"]
        assert client.post("/v1/session/pair", headers=origin, json={"code": old_code}).status_code == 401
        assert (
            client.get(
                "/v1/activity", headers={"Cookie": "; ".join(f"{key}={value}" for key, value in cookies.items())}
            ).status_code
            == 401
        )
        caps = client.get("/v1/mission/capabilities", headers=bearer).json()
        assert caps["offline_ask_enabled"] is True and caps["build_review_enabled"] is False
        assert caps["dispatch_authority"] == "NONE"
        assert client.get("/v1/local/status", headers=bearer).json()["profiles"] == "DISABLED"
        assert client.post("/v2/ask", headers=bearer, json={}).status_code == 503
        assert client.post("/v1/goals", headers=bearer, json={}).status_code == 404
        assert (
            client.post("/v1/mission/goals/synthetic/build-review/decision", headers=bearer, json={}).status_code == 404
        )
    assert not calls and app.state.local_model.stopped_fixture
    with pytest.raises(LocalApplicationRejected, match="mission_ask_scope_unavailable"):
        local_server.build_local_app(
            config.model_copy(update={"bind_host": "::1"}), settings, token, mission_assets=ASSETS
        )
    with pytest.raises(LocalApplicationRejected, match="mission_ask_scope_unavailable"):
        local_server.build_local_app(config, settings, token, mission_assets=ASSETS, profiles=object())
    # The metadata-only factory cannot be turned into an Ask runtime by the UI mount.
    from panestria.api.activity_server import build_activity_app

    observation = ActivitySettings(
        schema_version=1,
        owner_id=config.owner_id,
        project_id=config.project_id,
        token_file=config.token_file,
        bind_port=config.bind_port,
    )
    observer = build_activity_app(observation, settings, token)
    try:
        with pytest.raises(LocalApplicationRejected, match="mission_ask_scope_unavailable"):
            mount_mission_control(observer, observation, token, ASSETS, offline_ask=True)
    finally:
        observer.state.health.shutdown()


def test_browser_offline_ask_answer_cancel_recovery_and_refusal(ask_application, tmp_path, record_property):
    path, config, token, settings, app, calls = ask_application
    record_property("mode", "ACTUAL_CHROMIUM_HTTP_PG__TEST_FIXTURE_NOT_LIVE_MODEL_PROCESS_HARDWARE")
    listener = local_server.owned_listener(config)
    server = uvicorn.Server(uvicorn.Config(app, log_config=None, access_log=False, http=LocalHttpProtocol))
    thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 15
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline, "local test server failed startup"
            time.sleep(0.02)
        code = subprocess.run(
            [str(ROOT / ".venv/bin/python"), "-m", "panestria.cli.main", "local", "pair-code", "--config", str(path)],
            cwd=ROOT,
            env={**os.environ, "PANESTRIA_DATABASE_URL": settings.database_url.get_secret_value()},
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert code.returncode == 0 and token not in code.stdout, code.stderr
        fixture = tmp_path / "browser.json"
        fixture.write_text(json.dumps({"origin": config.origin, "code": json.loads(code.stdout)["code"]}))
        fixture.chmod(0o600)
        screenshot = tmp_path / "offline-ask.png"
        result = subprocess.run(
            [os.environ.get("PANESTRIA_TEST_NODE", "node"), "tests/offline-ask.mjs"],
            cwd=ROOT / "apps/mission-control",
            env={
                **os.environ,
                "PANESTRIA_BROWSER_FIXTURE": str(fixture),
                "PANESTRIA_BROWSER_SCREENSHOT": str(screenshot),
            },
            capture_output=True,
            text=True,
            timeout=80,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        outcomes = json.loads(result.stdout)
        assert len(calls) == 4  # completion, explicit cancel, disconnected cancel, unavailable; no retry/fallback
        with psycopg.connect(settings.database_url.get_secret_value()) as db:
            rows = db.execute(
                "SELECT id,state,metadata FROM panestria.ask_request WHERE project_id=%s ORDER BY created_at",
                (config.project_id,),
            ).fetchall()
        assert {str(row[0]): row[1] for row in rows} == outcomes
        assert sorted(outcomes.values()) == ["CANCELLED", "CANCELLED", "COMPLETED", "UNAVAILABLE"]
        assert ANSWER not in json.dumps(rows, default=str)
        target = os.environ.get("PANESTRIA_MISSION_SCREENSHOT")
        if target:
            import shutil

            shutil.copyfile(screenshot, target)
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive()
    assert app.state.local_model.stopped_fixture and app.state.ask_api.governor.stopped
