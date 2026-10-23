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
            for method in (client.post, client.delete):
                assert (
                    method(
                        "/v1/activity/storage",
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
