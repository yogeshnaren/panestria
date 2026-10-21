"""Actual PTY/HTTP/PG task pane; model output is the existing explicit fixture."""

import curses
import os

import psycopg
from test_ask_tui import terminal
from test_ask_tui import terminal_server as terminal_server  # noqa: F401
from test_local_server import configured as configured  # noqa: F401
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401
from test_owner_build_cli import owner_cli as owner_cli  # noqa: F401


def test_actual_project_task_pane_observes_running_ask_without_cancelling_or_starting_another(terminal_server):
    f = terminal_server
    f.state.delay = True
    with terminal(f.config) as t:
        t.until(b"CONNECTED")
        os.write(t.master, b"nPUBLIC activity question\n")
        assert f.state.started.wait(3)
        with psycopg.connect(f.dsn) as c:
            identity, state = c.execute(
                "SELECT id,state FROM panestria.ask_request WHERE owner_id=%s AND project_id=%s "
                "ORDER BY created_at DESC LIMIT 1",
                (str(f.settings.owner_id), str(f.settings.project_id)),
            ).fetchone()
        assert state == "RUNNING"
        os.write(t.master, b"t")
        t.until(b"PROJECT TASKS")
        t.until(str(identity)[:8].encode())
        assert f.state.calls == 1
        # These controls must have no mutation meaning inside the read-only pane.
        curses.setupterm(term="xterm-256color")
        os.write(t.master, b"c" + curses.tigetstr("kf6") + b"tr")
        t.until(b"Unretained answer text")
        with psycopg.connect(f.dsn) as c:
            assert c.execute("SELECT state FROM panestria.ask_request WHERE id=%s", (identity,)).fetchone() == (
                "RUNNING",
            )
        assert f.state.calls == 1
        # Returning to Ask restores its existing explicit cancellation action.
        os.write(t.master, b"c")
        t.until(b"CANCELLED")
        os.write(t.master, b"q")


def test_standalone_metadata_terminal_needs_no_model_and_mounts_no_mutations(prepared_plan, tmp_path):
    import json
    import signal
    import socket
    import subprocess
    import time
    from pathlib import Path
    from uuid import uuid4

    import httpx2 as httpx
    from typer.testing import CliRunner

    from panestria.cli.main import app
    from panestria.config_activity import load_activity_settings

    _, owner, _, plan = prepared_plan
    root = Path(__file__).resolve().parents[2]
    directory = tmp_path / "metadata-only"
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    args = [
        "activity",
        "init",
        "--directory",
        str(directory),
        "--owner-id",
        owner.actor.owner_id,
        "--project-id",
        owner.actor.project_id,
        "--port",
        str(port),
    ]
    runner = CliRunner()
    initialized = runner.invoke(app, args)
    assert initialized.exit_code == 0, initialized.output
    assert json.loads(initialized.stdout)["project_created"] is False
    path = directory / "activity.json"
    config, token = load_activity_settings(path)
    originals = {p.name: p.read_bytes() for p in directory.iterdir()}
    assert runner.invoke(app, args).exit_code == 0
    conflict = [*args]
    conflict[conflict.index("--project-id") + 1] = str(uuid4())
    assert runner.invoke(app, conflict).exit_code == 2
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == originals
    assert token.get_secret_value() not in initialized.stdout
    assert "model_cache" not in path.read_text()
    with owner.connect() as c:
        before = c.execute("SELECT count(*) FROM panestria.task_event").fetchone()
    server = subprocess.Popen(
        [str(root / ".venv/bin/python"), "-m", "panestria.cli.main", "activity", "serve", "--config", str(path)],
        cwd=root,
        env={**os.environ, "PANESTRIA_DATABASE_URL": owner.dsn},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        with httpx.Client(trust_env=False, timeout=2) as client:
            deadline = time.monotonic() + 10
            while True:
                assert server.poll() is None and time.monotonic() < deadline
                try:
                    response = client.get(config.origin + "/healthz")
                    if response.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.02)
            headers = {"Authorization": "Bearer " + token.get_secret_value()}
            page = client.get(config.origin + "/v1/activity", headers=headers)
            assert page.status_code == 200 and plan.goal_id in page.text
            assert client.get(config.origin + "/v1/activity").status_code == 401
            for route in ("/v1/ask", "/v1/goals", "/v1/approvals", "/v1/session/code"):
                assert client.post(config.origin + route, headers=headers, json={}).status_code == 404
            # The actual CLI server refuses an occupied port without disturbing the running one.
            occupied = runner.invoke(app, ["activity", "serve", "--config", str(path)])
            assert occupied.exit_code == 2 and "local_bind_unavailable" in occupied.output
            assert client.get(config.origin + "/v1/activity", headers=headers).status_code == 200
            with terminal(path, entry=("activity", "tui")) as t:
                t.until(b"PROJECT TASKS")
                t.until(plan.goal_id[:8].encode())
                assert b"FRESH" in t.transcript
                os.write(t.master, b"1")
                t.until(b"GOAL TIMELINE")
                t.until(b"Canonical goal:", after=0)
                t.until(b"Canonical snapshot plus event metadata", after=0)
                assert b"PRIVATE_ACTIVITY" not in t.transcript
                os.write(t.master, b"c")  # No cancellation in this read-only view.
                os.write(t.master, b"b")
                t.until(b"PROJECT TASKS")
                os.write(t.master, b"nct")  # No Ask/edit/cancel pane exists in this profile.
                os.write(t.master, b"r")
                t.until(b"FRESH", after=0)
                os.write(t.master, b"q")
        with owner.connect() as c:
            assert c.execute("SELECT count(*) FROM panestria.task_event").fetchone() == before
    finally:
        if server.poll() is None:
            server.send_signal(signal.SIGINT)  # Only this fixture's exact foreground child.
        out, err = server.communicate(timeout=8)
        assert server.returncode in {0, 130}, err  # SIGINT is a normal foreground stop.
        assert token.get_secret_value().encode() not in out + err
