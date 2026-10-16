"""Actual owned loopback HTTP→API→Postgres roundtrip; no provider/model."""

import json
import threading
import time

import psycopg
import uvicorn
from typer.testing import CliRunner

from panestria.api.auth import GoalApi
from panestria.api.main import create_app, mount_goal_api
from panestria.cli.main import app
from panestria.config import Settings
from quota_support import observation


def test_actual_cli_report_show_current_and_replay_through_owned_http_listener(r1_task, tmp_path):
    token = "synthetic-owned-quota-cli-token"
    token_file = tmp_path / "token"
    token_file.write_text(token)
    token_file.chmod(0o600)
    body = observation()
    payload = {"schema_version": 1, "task_id": r1_task["task"], "observation": body.model_dump(mode="json")}
    source = tmp_path / "quota.json"
    source.write_text(json.dumps(payload))
    source.chmod(0o600)
    application = create_app(Settings(database_url=r1_task["dsn"]), lambda _: None)
    mount_goal_api(application, GoalApi(token, r1_task["owner"], r1_task["project"], r1_task["dsn"]))
    server = uvicorn.Server(
        uvicorn.Config(application, host="127.0.0.1", port=0, log_level="critical", access_log=False)
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline, "owned_quota_http_start_failed"
            time.sleep(0.01)
        port = server.servers[0].sockets[0].getsockname()[1]
        shared = ["--token-file", str(token_file), "--base-url", f"http://127.0.0.1:{port}"]
        runner = CliRunner()
        commands = [
            ["report", "--input-file", str(source)],
            ["show", body.observation_id],
            ["current", "--account-ref", body.scope.account_ref, "--window", "session"],
            ["report", "--input-file", str(source)],
        ]
        for command in commands:
            result = runner.invoke(app, ["quota", *command, *shared])
            assert result.exit_code == 0, result.output
            assert token not in result.output and "OBSERVATION_ONLY" in result.output
            displayed = json.loads(result.output)
            if "lanes" in displayed:
                displayed = displayed["lanes"][0]
            assert displayed["effective_remaining"] == "40" and displayed["observation"] == body.model_dump(mode="json")
        payload["observation"]["remaining"] = "41"
        source.write_text(json.dumps(payload))
        rejected = runner.invoke(app, ["quota", "report", "--input-file", str(source), *shared])
        assert rejected.exit_code == 2 and rejected.output.strip() == "quota_input_or_api_unavailable"
        with psycopg.connect(r1_task["dsn"]) as c:
            assert c.execute(
                "SELECT count(*) FROM panestria.quota_observation WHERE task_id=%s", (r1_task["task"],)
            ).fetchone() == (1,)
            assert c.execute(
                "SELECT count(*) FROM panestria.task_event WHERE task_id=%s AND kind='quota.observed'",
                (r1_task["task"],),
            ).fetchone() == (1,)
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        assert not thread.is_alive(), "owned_quota_http_shutdown_failed"
