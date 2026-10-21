"""Synthetic owner HTTP/OS-key/local-model qualification on an isolated bus."""

from __future__ import annotations

import hashlib
import json
import os
import resource
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

import httpx2 as httpx
import psycopg
import uvicorn
from profile_keyring_probe import stop, wait_name

from panestria.api.local_server import build_local_app, owned_listener, server_config
from panestria.api.routes.profiles import ProfileApi
from panestria.config import Settings
from panestria.config_local import LocalApplicationSettings
from panestria.inference.local import LocalProvider
from panestria.kernel.local_setup import LocalSetupIntent, LocalSetupService
from panestria.kernel.uow import UnitOfWork
from panestria.memory.keys import ProfileKeyHandle, SecretServiceProfileKeys
from panestria.memory.vault import ProfileVault


class ObservedLocalProvider(LocalProvider):
    calls = 0

    async def agenerate(self, request):
        self.calls += 1
        return await super().agenerate(request)


def main() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    root = Path(sys.argv[1]).resolve(strict=True)
    assert os.environ.get("PANESTRIA_ISOLATED_KEYRING") == str(root)
    for name, directory in (("XDG_DATA_HOME", "data"), ("XDG_CONFIG_HOME", "config"), ("XDG_RUNTIME_DIR", "runtime")):
        assert os.environ.get(name) == str(root / directory)
        assert (root / directory).stat().st_mode & 0o077 == 0
    daemon = subprocess.Popen(
        [sys.argv[2], "--foreground", "--unlock", "--components=secrets", f"--control-directory={root / 'control'}"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert daemon.stdin is not None
        daemon.stdin.write(secrets.token_bytes(32).hex().encode() + b"\n")
        daemon.stdin.close()
        wait_name(True)
        dsn, cache = sys.argv[3:5]
        owner, project = str(uuid4()), str(uuid4())
        handle = ProfileKeyHandle(owner_id=owner, project_id=project, profile_id=str(uuid4()), key_id=str(uuid4()))
        keys = SecretServiceProfileKeys()
        keys.provision(handle)
        import socket

        with socket.socket() as available:
            available.bind(("127.0.0.1", 0))
            port = available.getsockname()[1]
        config = LocalApplicationSettings.model_validate_json(
            json.dumps(
                {
                    "schema_version": 1,
                    "owner_id": owner,
                    "project_id": project,
                    "bind_port": port,
                    "model_cache": cache,
                    "token_file": str(root / "unused-token"),
                    "runtime_directory": str(root / "service"),
                }
            )
        )
        settings = Settings(database_url=dsn, bind_port=port).validate_profile()
        with psycopg.connect(dsn) as c:
            LocalSetupService().initialize(
                UnitOfWork(c),
                LocalSetupIntent.model_validate_json(
                    json.dumps(
                        {
                            "owner_id": owner,
                            "project_id": project,
                            "intent": "OFFLINE_ASK",
                        }
                    )
                ),
            )
        token = secrets.token_urlsafe(32)
        app = build_local_app(config, settings, token, profiles=ProfileApi(ProfileVault(keys, enabled=True)))
        provider = ObservedLocalProvider(app.state.local_model.socket_path)
        app.state.ask_api.provider = provider
        listener = owned_listener(config)
        server = uvicorn.Server(server_config(app))
        worker = threading.Thread(target=server.run, kwargs={"sockets": [listener]})
        worker.start()
        try:
            deadline = time.monotonic() + 65
            while not server.started:
                assert worker.is_alive() and time.monotonic() < deadline, "actual_profile_server_not_started"
                time.sleep(0.05)
            actual = app.state.local_model.effective
            assert actual["HostConfig"]["NetworkMode"] == "none" and not actual["HostConfig"]["PortBindings"]
            assert actual["HostConfig"]["LogConfig"]["Type"] == "none"
            assert {limit["Name"]: (limit["Soft"], limit["Hard"]) for limit in actual["HostConfig"]["Ulimits"]}[
                "core"
            ] == (0, 0)
            destinations = {mount["Destination"] for mount in actual["Mounts"]}
            assert destinations == {
                "/usr/local/bin/ollama",
                "/usr/local/lib/ollama",
                "/models",
                "/bridge",
                "/runtime/bridge.py",
            }
            assert all(not mount["RW"] for mount in actual["Mounts"] if mount["Destination"] != "/bridge")
            assert not any(
                "DBUS_SESSION_BUS_ADDRESS=" in value or "PANESTRIA_DATABASE_URL=" in value
                for value in actual["Config"]["Env"]
            )
            with httpx.Client(base_url=config.origin, trust_env=False, follow_redirects=False, timeout=75) as client:
                check(client, token, config.origin, handle, provider, dsn)
        finally:
            server.should_exit = True
            worker.join(timeout=12)
            listener.close()
            assert not worker.is_alive(), "actual_profile_server_cleanup_unconfirmed"
            assert app.state.local_model.id is None and not app.state.local_model.socket_path.exists()
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "model_calls": provider.calls,
                    "actual_os_store": True,
                    "actual_local_model": True,
                    "physical_loopback_http": True,
                    "owned_model_cleanup": True,
                }
            )
        )
    finally:
        stop(daemon)


def check(client, token, origin_url, handle, provider, dsn):
    project = handle.project_id
    cli = {"Authorization": "Bearer " + token}
    assert client.get("/v1/local/status", headers=cli).json()["profiles"] == "EXPLICITLY_ENABLED"
    assert client.post("/v1/goals", json={}, headers=cli).status_code == 404
    sentinel = "LIVE_SYNTHETIC_PRIVATE_STYLE: use brief plain-language answers"
    created = client.post(
        "/v2/profiles",
        headers=cli,
        json={
            "schema_version": 1,
            "profile_id": handle.profile_id,
            "key_id": handle.key_id,
            "intent": "SAVE_RESTRICTED_PROFILE",
            "document": {"fields": {"communication": sentinel}, "approved_for_local_context": ["communication"]},
        },
    )
    assert created.status_code == 201, "live_profile_create_failed"
    code = client.post("/v1/session/code", json={}, headers=cli).json()["code"]
    origin = {"Origin": origin_url}
    paired = client.post("/v1/session/pair", json={"code": code}, headers=origin)
    assert paired.status_code == 200
    headers = {**origin, "X-Panestria-CSRF": paired.json()["csrf_token"]}
    request = {
        "schema_version": 2,
        "request_id": str(uuid4()),
        "project_id": project,
        "question": "Reply with only the word READY.",
        "context_tokens": 4096,
        "max_output_tokens": 32,
        "deadline_seconds": 60.0,
        "profile": {
            "profile_id": handle.profile_id,
            "expected_row_version": 0,
            "fields": ["communication"],
            "purpose": "RESPONSE_STYLE",
            "destination": "OFFLINE_LOCAL_MODEL",
        },
    }
    response = client.post("/v2/ask", json=request, headers=headers)
    assert response.status_code == 200, "live_profile_ask_failed:" + str(response.status_code)
    body = response.json()
    assert body["state"] == "COMPLETED" and body["text"].strip()
    assert "READY" in body["text"].upper(), "live_model_instruction_not_satisfied"
    assert body["privacy_label"] == "RESTRICTED" and body["offline"] is True
    assert body["response_sha256"] is None and body["response_digest_mode"] == "OMITTED_RESTRICTED_PROFILE"
    assert provider.calls == 1
    with psycopg.connect(dsn) as c:
        for table in ("profile_revision", "context_pack", "ask_profile_context", "ask_request", "learning_record"):
            rows = c.execute(f"SELECT row_to_json(t)::text FROM panestria.{table} t").fetchall()
            assert all(
                sentinel not in row[0] and hashlib.sha256(sentinel.encode()).hexdigest() not in row[0] for row in rows
            )
    hidden = client.post(
        f"/v2/profiles/{handle.profile_id}/suppress",
        json={"schema_version": 1, "expected_version": 0},
        headers=headers,
    )
    assert hidden.status_code == 200
    request["request_id"] = str(uuid4())
    denied = client.post("/v2/ask", json=request, headers=headers)
    assert denied.json()["code"] == "profile_suppressed" and provider.calls == 1


if __name__ == "__main__":
    main()
