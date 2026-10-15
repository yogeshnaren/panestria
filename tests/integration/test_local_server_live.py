"""Actual CLI, TCP HTTP and constrained local engine; synthetic content only."""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from uuid import uuid4

import httpx2 as httpx
import psycopg
import pytest

from panestria.config_local import create_local_token
from panestria.kernel.local_setup import LocalSetupIntent, LocalSetupService
from panestria.kernel.uow import UnitOfWork


@pytest.mark.live
def test_actual_cli_local_ask_restart_and_owned_shutdown(r1_database, tmp_path, record_property):
    cache = os.environ.get("PANESTRIA_PROFILE_TEST_MODEL_CACHE")
    if not cache:
        pytest.skip("explicit existing read-only public model cache required; not qualified")
    if sys.platform != "linux":
        pytest.skip("Linux runtime required; not qualified")
    intent = LocalSetupIntent(owner_id=str(uuid4()), project_id=str(uuid4()), intent="OFFLINE_ASK")
    with psycopg.connect(r1_database) as c:
        LocalSetupService().initialize(UnitOfWork(c), intent)
    token_file = tmp_path / "local-token"
    create_local_token(token_file)
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    path = tmp_path / "local.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "owner_id": str(intent.owner_id),
                "project_id": str(intent.project_id),
                "bind_port": port,
                "token_file": str(token_file),
                "model_cache": cache,
                "runtime_directory": str(tmp_path / "runtime"),
            }
        )
    )
    path.chmod(0o600)
    env = {key: os.environ[key] for key in ("PATH", "HOME", "LANG", "LD_LIBRARY_PATH") if key in os.environ}
    env["PANESTRIA_DATABASE_URL"] = r1_database
    command = [sys.executable, "-m", "panestria.cli.main", "local", "serve", "--config", str(path)]
    cli = {"Authorization": "Bearer " + token_file.read_text().strip()}
    question = "Reply with only the word READY. SYNTHETIC_LOCAL_SERVER_PRIVATE_SENTINEL"
    request = {
        "request_id": str(uuid4()),
        "project_id": str(intent.project_id),
        "question": question,
        "context_tokens": 2048,
        "max_output_tokens": 32,
    }
    original_models = subprocess.check_output(
        ["docker", "ps", "-a", "-q", "--no-trunc", "--filter", "label=panestria.purpose=local-model"],
        text=True,
    ).split()
    assert original_models == [], "existing_model_service_preserved; qualification not run"
    browser = httpx.Client(base_url=origin, trust_env=False, timeout=65)
    try:
        for run in range(2):
            child = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 65
                while True:
                    assert child.poll() is None, "actual_local_server_startup_failed"
                    try:
                        ready = browser.get("/v1/local/status", headers=cli, timeout=1)
                        if ready.status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    assert time.monotonic() < deadline, "actual_server_startup_deadline"
                    time.sleep(0.1)
                assert ready.json()["model_socket_present"] and ready.json()["profiles"] == "DISABLED"
                assert ready.json()["runtime_certified"] is False
                if run == 0:
                    code = browser.post("/v1/session/code", json={}, headers=cli).json()["code"]
                    paired = browser.post("/v1/session/pair", json={"code": code}, headers={"Origin": origin})
                    csrf = paired.json()["csrf_token"]
                    headers = {"Origin": origin, "X-Panestria-CSRF": csrf}
                    assert browser.post("/v1/ask", json=request, headers={"Origin": origin}).status_code == 403
                    response = browser.post("/v1/ask", json=request, headers=headers)
                    assert response.status_code == 200, "actual_local_inference_failed:" + str(response.status_code)
                    body = response.json()
                    assert body["state"] == "COMPLETED" and "READY" in body["text"].upper()
                    assert body["offline"] is True and body["response_retained"] is False
                    assert browser.get("/healthz", headers={"Host": "attacker.invalid"}).status_code == 403
                    assert browser.get("/healthz?token=SYNTHETIC_SECRET").status_code == 400
                    assert browser.post("/v2/profiles", json={}, headers=headers).status_code == 404
                    # A second launcher must fail at bind before owning any model.
                    conflict = subprocess.run(command, env=env, capture_output=True, text=True, timeout=10)
                    assert conflict.returncode == 2 and "local_bind_unavailable" in conflict.stderr
                    assert browser.get("/v1/local/status", headers=cli).status_code == 200
                else:
                    # Stable local token retains scoped session/CSRF after restart.
                    replay = browser.post("/v1/ask", json=request, headers=headers)
                    assert replay.status_code == 200 and replay.json()["replayed_receipt"]
                    assert "text" not in replay.json()
                    assert browser.post("/v1/session/logout", json={}, headers=headers).status_code == 200
                    denied = browser.post("/v1/ask", json={**request, "request_id": str(uuid4())}, headers=headers)
                    assert denied.status_code == 403
            finally:
                child.send_signal(signal.SIGINT) if child.poll() is None else None
                try:
                    stdout, stderr = child.communicate(timeout=15)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.communicate(timeout=3)
                    pytest.fail("actual_owned_shutdown_deadline")
                assert question.encode() not in stdout + stderr
                assert token_file.read_bytes().strip() not in stdout + stderr
                assert r1_database.encode() not in stdout + stderr
            assert not (tmp_path / "runtime/model/model.sock").exists()
            remaining = subprocess.check_output(
                ["docker", "ps", "-a", "-q", "--no-trunc", "--filter", "label=panestria.purpose=local-model"],
                text=True,
            ).split()
            assert remaining == original_models, "owned_model_cleanup_failed"
        with psycopg.connect(r1_database) as c:
            for table in ("ask_request", "context_pack", "learning_record"):
                assert all(
                    question not in row[0]
                    for row in c.execute(
                        f"SELECT row_to_json(t)::text FROM panestria.{table} t",
                    )
                )
    finally:
        browser.close()
    record_property("execution_mode", "ACTUAL_CLI_TCP_HTTP_POSTGRES_OFFLINE_CPU_MODEL")
    record_property("mock_provider_or_model", False)
    record_property("restart_session_receipt_preserved", True)
    record_property("owned_runtime_shutdown", True)
    record_property("paid_provider_calls", 0)
    record_property("release_gate", "NOT_EVALUATED")
