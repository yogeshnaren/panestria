"""Actual private PG/browser-session/statvfs path; no model/provider or cleanup."""

import time

import psycopg
import pytest
from fastapi.testclient import TestClient
from test_mission_control_browser import ASSETS, configure

from panestria.api.activity_server import build_activity_app
from panestria.api.mission_web import mount_mission_control
from panestria.config import Settings
from panestria.config_local import LocalApplicationRejected
from panestria.resources.storage import StorageSettings


def paired(client, origin, token):
    code = client.post("/v1/session/code", headers={"Authorization": "Bearer " + token}, json={}).json()["code"]
    result = client.post("/v1/session/pair", headers={"Origin": origin}, json={"code": code})
    assert result.status_code == 200
    return result.json()


def test_explicit_host_storage_mode_requires_fresh_pairing_and_preserves_owner_data(
    r1_migration_task, tmp_path, record_property
):
    f = r1_migration_task
    _, config, token = configure(f, tmp_path)
    private = tmp_path / "PRIVATE_STORAGE_SELECTION"
    private.mkdir(mode=0o700)
    payload = private / "preserve.txt"
    payload.write_bytes(b"PRIVATE_CONTENT_MUST_NOT_BE_READ_OR_REMOVED")
    path = tmp_path / "config/storage.json"
    body = StorageSettings(notifications_enabled=True, filesystem=private, minimum_free_bytes=2**63 - 1)
    path.write_text(body.model_dump_json())
    path.chmod(0o600)
    settings = Settings(database_url=f["dsn"]).validate_profile()
    ordinary = build_activity_app(config, settings, token, storage_config=path)
    mount_mission_control(ordinary, config, token, ASSETS)
    app = build_activity_app(config, settings, token, storage_config=path)
    with pytest.raises(LocalApplicationRejected, match="mission_storage_select_one_mode"):
        mount_mission_control(app, config, token, ASSETS, storage_mode=True, build_intake=True)
    mount_mission_control(app, config, token, ASSETS, storage_mode=True)
    with psycopg.connect(f["dsn"]) as c:
        before = c.execute("SELECT count(*) FROM panestria.task_event").fetchone()
    record_property("scope", "Actual PG/cookies/ASGI/statvfs; synthetic warning threshold; no live pressure/provider")
    try:
        with TestClient(ordinary, base_url=config.origin) as old, TestClient(app, base_url=config.origin) as client:
            paired(old, config.origin, token)
            assert old.get("/v1/activity/storage").status_code == 403
            assert "storage_status_enabled" not in old.get("/v1/mission/capabilities").json()
            old_cookie = old.cookies.get(ordinary.state.browser_access.cookie_name)
            assert ordinary.state.browser_access.cookie_name != app.state.browser_access.cookie_name
            assert (
                client.get(
                    "/v1/activity/storage", headers={"Cookie": app.state.browser_access.cookie_name + "=" + old_cookie}
                ).status_code
                == 401
            )
            session = paired(client, config.origin, token)
            capabilities = client.get("/v1/mission/capabilities").json()
            assert capabilities["storage_status_enabled"] is True and capabilities["dispatch_authority"] == "NONE"
            assert not any(
                capabilities[k]
                for k in ("build_run_enabled", "build_intake_enabled", "offline_ask_enabled", "research_intake_enabled")
            )
            deadline = time.monotonic() + 6
            while True:
                response = client.get("/v1/activity/storage")
                assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
                result = response.json()
                if result["state"] == "OBSERVED":
                    break
                assert time.monotonic() < deadline
                time.sleep(0.02)
            assert result["capacity"]["available_bytes"] > 0
            assert "free_reserve_at_risk" in {w["code"] for w in result["warnings"]}
            assert result["cleanup_authority"] == result["acceptance_authority"] == "NONE"
            assert result["scope"] == "OWNER_HOST_METADATA_NOT_PROJECT_ATTRIBUTION"
            assert (
                str(private) not in response.text
                and token not in response.text
                and "PRIVATE_CONTENT" not in response.text
            )
            for method in ("POST", "DELETE"):
                assert (
                    client.request(
                        method,
                        "/v1/activity/storage",
                        json={},
                        headers={"Origin": config.origin, "X-Panestria-CSRF": session["csrf_token"]},
                    ).status_code
                    == 405
                )
            assert client.get("/v1/activity/storage", headers={"Origin": "https://foreign.invalid"}).status_code == 403
            assert client.post("/v1/ask", json={}).status_code == 404
            assert (
                client.post(
                    "/v1/session/logout",
                    headers={"Origin": config.origin, "X-Panestria-CSRF": session["csrf_token"]},
                    json={},
                ).status_code
                == 200
            )
            assert client.get("/v1/activity/storage").status_code == 401
        assert payload.read_bytes() == b"PRIVATE_CONTENT_MUST_NOT_BE_READ_OR_REMOVED"
        assert path.read_text() == body.model_dump_json()
        with psycopg.connect(f["dsn"]) as c:
            assert c.execute("SELECT count(*) FROM panestria.task_event").fetchone() == before
    finally:
        ordinary.state.storage_observer.close()
        app.state.storage_observer.close()
        ordinary.state.health.shutdown()
        app.state.health.shutdown()


def test_actual_chromium_storage_notices_optout_and_revoke_clear_host_view(
    r1_migration_task, tmp_path, record_property
):
    import json
    import os
    import select
    import socket
    import subprocess
    import threading

    import httpx2 as httpx
    import uvicorn

    from panestria.api.local_server import server_config

    f = r1_migration_task
    _, config, token = configure(f, tmp_path)
    private = tmp_path / "PRIVATE_STORAGE_SELECTION"
    private.mkdir(mode=0o700)
    storage = tmp_path / "config/storage.json"
    settings = StorageSettings(
        notifications_enabled=True,
        filesystem=private,
        minimum_free_bytes=2**63 - 1,
        history_directory=tmp_path / "retained-history",
    )
    storage.write_text(settings.model_dump_json())
    storage.chmod(0o600)
    app = build_activity_app(config, Settings(database_url=f["dsn"]).validate_profile(), token, storage_config=storage)
    mount_mission_control(app, config, token, ASSETS, storage_mode=True)
    listener = socket.socket()
    listener.bind(("127.0.0.1", config.bind_port))
    server = uvicorn.Server(server_config(app))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]})
    thread.start()
    browser = None
    record_property(
        "scope", "Actual Chromium/PG/HTTP/statvfs; synthetic reserve threshold and forced next-settings tick"
    )
    try:
        deadline = time.monotonic() + 8
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline
            time.sleep(0.02)
        with httpx.Client(trust_env=False, timeout=3) as client:
            code = client.post(
                config.origin + "/v1/session/code", headers={"Authorization": "Bearer " + token}, json={}
            ).json()["code"]
        fixture = tmp_path / "browser.json"
        fixture.write_text(json.dumps({"origin": config.origin, "code": code}))
        fixture.chmod(0o600)
        screenshot = tmp_path / "storage.png"
        browser = subprocess.Popen(
            [os.environ.get("PANESTRIA_TEST_NODE", "node"), "tests/storage.mjs"],
            cwd=ASSETS.parent,
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
            ready, _, _ = select.select([browser.stdout], [], [], 45)
            assert ready, f"browser did not reach {expected}"
            observed = browser.stdout.readline().strip()
            if observed != expected:
                browser.wait(timeout=5)
                raise AssertionError(f"browser expected {expected}, got {observed}: " + browser.stderr.read())

        def advance():
            browser.stdin.write("{}\n")
            browser.stdin.flush()

        wait("OBSERVED")
        assert len(list(settings.history_directory.glob("*.json"))) == 1
        storage.write_text(settings.model_copy(update={"notifications_enabled": False}).model_dump_json())
        observer = app.state.storage_observer
        with observer.lock:
            observer.next_check = 0  # Explicit timer seam: real file opt-out; do not wait a whole minute in CI.
        advance()
        wait("DISABLED")
        with psycopg.connect(f["dsn"]) as c:
            c.execute("UPDATE panestria.browser_session SET revoked_at=now() WHERE project_id=%s", (f["project"],))
        advance()
        wait("PASS")
        browser.communicate(timeout=8)
        assert browser.returncode == 0 and screenshot.is_file()
        target = os.environ.get("PANESTRIA_STORAGE_SCREENSHOT")
        if target:
            import shutil

            shutil.copyfile(screenshot, target)
    finally:
        if browser is not None and browser.poll() is None:
            browser.terminate()
            browser.communicate(timeout=8)
        server.should_exit = True
        thread.join(timeout=8)
        listener.close()
        app.state.storage_observer.close()
        app.state.health.shutdown()
        assert not thread.is_alive()
