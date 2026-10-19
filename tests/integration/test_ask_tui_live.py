"""One explicit synthetic terminal journey through the actual existing local model."""

import json
import os
import signal
import socket
import subprocess
import sys
import time

import httpx2 as httpx
import psycopg
import pytest
from test_ask_tui import terminal

from panestria.config_local import create_local_token
from panestria.kernel.local_setup import LocalSetupIntent, LocalSetupService
from panestria.kernel.uow import UnitOfWork


@pytest.mark.live
def test_actual_terminal_answers_with_existing_local_cpu_model(r1_database, tmp_path, record_property):
    from uuid import uuid4

    cache = os.environ.get("PANESTRIA_PROFILE_TEST_MODEL_CACHE")
    if not cache or sys.platform != "linux":
        pytest.skip("Existing explicit local model cache and Linux required; not qualified")
    original = subprocess.check_output(
        ["docker", "ps", "-a", "-q", "--no-trunc", "--filter", "label=panestria.purpose=local-model"], text=True
    ).split()
    assert not original, "Existing controller preserved; actual terminal/model check not run"
    intent = LocalSetupIntent(owner_id=str(uuid4()), project_id=str(uuid4()), intent="OFFLINE_ASK")
    with psycopg.connect(r1_database) as c:
        LocalSetupService().initialize(UnitOfWork(c), intent)
    token = tmp_path / "local-token"
    create_local_token(token)
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    config = tmp_path / "local.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "owner_id": str(intent.owner_id),
                "project_id": str(intent.project_id),
                "bind_port": port,
                "token_file": str(token),
                "model_cache": cache,
                "runtime_directory": str(tmp_path / "runtime"),
            }
        )
    )
    config.chmod(0o600)
    env = {key: os.environ[key] for key in ("PATH", "HOME", "LANG", "LD_LIBRARY_PATH") if key in os.environ}
    env["PANESTRIA_DATABASE_URL"] = r1_database
    child = subprocess.Popen(
        [sys.executable, "-m", "panestria.cli.main", "local", "serve", "--config", str(config)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 65
        with httpx.Client(trust_env=False, timeout=1) as client:
            while True:
                assert child.poll() is None, "Actual local server did not start; model/resources unavailable"
                try:
                    response = client.get(
                        f"http://127.0.0.1:{port}/v1/local/status",
                        headers={"Authorization": "Bearer " + token.read_text().strip()},
                    )
                    if response.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                assert time.monotonic() < deadline, "Actual server startup deadline"
                time.sleep(0.1)
        with terminal(config) as t:
            t.until(b"CONNECTED")
            os.write(t.master, b"nReply with only the uppercase version of ready. PUBLIC synthetic terminal review.\r")
            t.until(b"COMPLETED", timeout=65)
            assert b"READY" in t.transcript
            assert token.read_bytes().strip() not in t.transcript and r1_database.encode() not in t.transcript
            os.write(t.master, b"q")
        with psycopg.connect(r1_database) as c:
            row = c.execute(
                "SELECT state,model_ref,metadata FROM panestria.ask_request WHERE project_id=%s",
                (str(intent.project_id),),
            ).fetchone()
            assert row[0] == "COMPLETED" and row[1] == "qwen2.5:1.5b-instruct"
            assert row[2] is not None
        record_property("execution_mode", "ACTUAL_PTY_KEYBOARD_HTTP_POSTGRES_NETWORK_NONE_CPU_MODEL")
        record_property("mock_provider_or_model", False)
        record_property("paid_provider_calls", 0)
        record_property("release_gate", "NOT_EVALUATED")
    finally:
        if child.poll() is None:
            child.send_signal(signal.SIGINT)
        try:
            stdout, stderr = child.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate(timeout=3)
            pytest.fail("Only the owned local launcher failed to stop within deadline")
        assert token.read_bytes().strip() not in stdout + stderr and r1_database.encode() not in stdout + stderr
        remaining = subprocess.check_output(
            ["docker", "ps", "-a", "-q", "--no-trunc", "--filter", "label=panestria.purpose=local-model"], text=True
        ).split()
        assert remaining == original and not (tmp_path / "runtime/model/model.sock").exists()
