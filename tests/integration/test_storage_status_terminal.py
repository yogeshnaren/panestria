"""Actual disposable PG/HTTP/CLI/PTY and filesystem; no model/provider/owner settings."""

import os
import signal
import socket
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

import httpx2 as httpx
import psycopg
from fastapi.testclient import TestClient
from test_ask_tui import terminal
from typer.testing import CliRunner

from panestria.api.activity_server import build_activity_app
from panestria.cli.main import app
from panestria.config import Settings
from panestria.config_activity import load_activity_settings
from panestria.resources.storage import StorageSettings

ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def foreground(config, storage, dsn, origin, token):
    server = subprocess.Popen(
        [
            str(ROOT / ".venv/bin/python"),
            "-m",
            "panestria.cli.main",
            "activity",
            "serve",
            "--config",
            str(config),
            "--storage-config",
            str(storage),
        ],
        cwd=ROOT,
        env={**os.environ, "PANESTRIA_DATABASE_URL": dsn},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        with httpx.Client(trust_env=False, timeout=2, headers={"Authorization": "Bearer " + token}) as client:
            deadline = time.monotonic() + 10
            while True:
                assert server.poll() is None and time.monotonic() < deadline
                try:
                    if client.get(origin + "/healthz").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.02)
            yield client
    finally:
        if server.poll() is None:
            server.send_signal(signal.SIGINT)  # Only this exact fixture child.
        out, err = server.communicate(timeout=8)
        assert server.returncode in {0, 130}, err
        assert token.encode() not in out + err


def test_owner_terminal_delivers_read_only_storage_warnings_and_disabled_settings_stop_sampling(
    r1_migration_task,
    tmp_path,
    record_property,
):
    f = r1_migration_task  # Dedicated database: no audit/restore fixture pollution.
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    directory = tmp_path / "terminal"
    result = CliRunner().invoke(
        app,
        [
            "activity",
            "init",
            "--directory",
            str(directory),
            "--owner-id",
            f["owner"],
            "--project-id",
            f["project"],
            "--port",
            str(port),
        ],
    )
    assert result.exit_code == 0, result.output
    path = directory / "activity.json"
    config, secret = load_activity_settings(path)
    token = secret.get_secret_value()
    storage = directory / "storage.json"
    data = tmp_path / "PRIVATE_STORAGE_PATH"
    data.mkdir()
    payload = data / "do-not-remove"
    payload.write_bytes(b"private payload is never read by the capacity probe")
    settings = StorageSettings(
        notifications_enabled=True,
        filesystem=data,
        minimum_free_bytes=2**63 - 1,  # Synthetic threshold, NOT real pressure.
    )
    storage.write_text(settings.model_dump_json())
    storage.chmod(0o600)
    originals = {p.name: p.read_bytes() for p in directory.iterdir()}
    with psycopg.connect(f["dsn"]) as c:
        before = c.execute("SELECT count(*) FROM panestria.task_event").fetchone()
    record_property("scope", "Actual PG/HTTP/CLI/PTY/statvfs; synthetic warning threshold; no live pressure/model")
    with foreground(path, storage, f["dsn"], config.origin, token) as client:
        assert client.get(config.origin + "/v1/activity/storage", headers={"Authorization": ""}).status_code == 401
        assert (
            client.get(
                config.origin + "/v1/activity/storage", headers={"Origin": "https://foreign.invalid"}
            ).status_code
            == 403
        )
        page = client.get(config.origin + "/v1/activity")
        assert page.status_code == 200 and page.json()["storage_available"] is True
        deadline = time.monotonic() + 6
        while True:
            status = client.get(config.origin + "/v1/activity/storage")
            assert status.status_code == 200 and status.headers["cache-control"] == "no-store"
            body = status.json()
            if body["state"] != "COLLECTING":
                break
            assert time.monotonic() < deadline
            time.sleep(0.02)
        assert body["state"] == "OBSERVED" and body["capacity"]["available_bytes"] > 0
        assert {v["code"] for v in body["warnings"]} >= {"free_reserve_at_risk"}
        assert body["components"] == [] and body["timeshift_status"] == "NOT_REQUESTED"
        assert body["cleanup_authority"] == body["acceptance_authority"] == "NONE"
        assert str(data) not in status.text and "filesystem" not in body["capacity"]
        assert "device" not in body["capacity"] and token not in status.text
        assert client.post(config.origin + "/v1/activity/storage", json={}).status_code == 405
        with terminal(path, entry=("activity", "tui")) as t:
            t.until(b"PROJECT TASKS")
            t.until(b"free_reserve_at_risk", after=0)
            os.write(t.master, b"o")
            t.until(b"HOST STORAGE")
            t.until(b"last free", after=0)
            import curses

            curses.setupterm(term="xterm-256color")
            os.write(t.master, curses.tigetstr("knp"))
            t.until(b"No deletion", after=0)
            assert b"PRIVATE_STORAGE_PATH" not in t.transcript and token.encode() not in t.transcript
            os.write(t.master, b"ncy")  # No cleanup/approval/inference actions exist in this view.
            os.write(t.master, b"b")
            t.until(b"PROJECT TASKS")
            os.write(t.master, b"q")
        assert {p.name: p.read_bytes() for p in directory.iterdir()} == originals
    # New explicit foreground run sees off before collecting, before a fresh
    # sample. No waiting sixty seconds or relabeling the old sample is needed.
    storage.write_text(settings.model_copy(update={"notifications_enabled": False}).model_dump_json())
    with foreground(path, storage, f["dsn"], config.origin, token) as client:
        deadline = time.monotonic() + 6
        while True:
            body = client.get(config.origin + "/v1/activity/storage").json()
            if body["state"] != "COLLECTING":
                break
            assert time.monotonic() < deadline
            time.sleep(0.02)
        assert body["state"] == "DISABLED" and body["capacity"] is None and body["observed_at"] is None
    assert payload.read_bytes() == b"private payload is never read by the capacity probe"
    with psycopg.connect(f["dsn"]) as c:
        assert c.execute("SELECT count(*) FROM panestria.task_event").fetchone() == before


def test_unconfigured_endpoint_has_no_probe_and_browser_host_metadata_is_refused(r1_migration_task, tmp_path):
    f = r1_migration_task
    directory = tmp_path / "scope"
    result = CliRunner().invoke(
        app,
        [
            "activity",
            "init",
            "--directory",
            str(directory),
            "--owner-id",
            f["owner"],
            "--project-id",
            f["project"],
        ],
    )
    assert result.exit_code == 0
    config, token = load_activity_settings(directory / "activity.json")
    application = build_activity_app(config, Settings(database_url=f["dsn"]), token.get_secret_value())
    with TestClient(application, base_url=config.origin) as client:
        headers = {"Authorization": "Bearer " + token.get_secret_value()}
        response = client.get("/v1/activity/storage", headers=headers)
        assert response.status_code == 200 and response.json()["state"] == "NOT_CONFIGURED"
        assert "storage_available" not in client.get("/v1/activity", headers=headers).json()
        application.state.browser_access = object()  # A browser-wired host may never disclose the view.
        response = client.get("/v1/activity/storage", headers=headers)
        assert response.status_code == 403 and response.json()["code"] == "storage_terminal_mode_only"
