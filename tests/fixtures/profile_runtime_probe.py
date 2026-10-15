"""Synthetic owner HTTP/OS-key/local-model qualification on an isolated bus."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from profile_keyring_probe import stop, wait_name

from panestria.api.auth import GoalApi
from panestria.api.main import create_app, mount_ask_api, mount_browser_api, mount_goal_api, mount_profile_api
from panestria.api.routes.ask import AskApi
from panestria.api.routes.profiles import ProfileApi
from panestria.api.sessions import BrowserAccess
from panestria.config import Settings
from panestria.inference.local import LocalProvider
from panestria.kernel.sessions import SessionService
from panestria.memory.keys import ProfileKeyHandle, SecretServiceProfileKeys
from panestria.memory.vault import ProfileVault
from panestria.resources.hardware import HardwareProbe


class ObservedLocalProvider(LocalProvider):
    calls = 0

    async def agenerate(self, request):
        self.calls += 1
        return await super().agenerate(request)


def main() -> None:
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
        dsn, owner, project = sys.argv[3:6]
        handle = ProfileKeyHandle(owner_id=owner, project_id=project, profile_id=str(uuid4()), key_id=str(uuid4()))
        keys = SecretServiceProfileKeys()
        keys.provision(handle)
        app = create_app(Settings(database_url=dsn, bind_port=8766), lambda deadline: None)
        token = "test-only-cli-token-at-least-16"
        mount_goal_api(app, GoalApi(token, owner, project, dsn))
        mount_browser_api(
            app, BrowserAccess("http://127.0.0.1:8766", SessionService(b"test-only-key-not-a-real-secret!!"), dsn)
        )
        provider = ObservedLocalProvider(Path(sys.argv[6]))
        archive = Path(__file__).resolve().parents[2] / "docs/specification/attachments/agentos-skills-v0.1.0.zip"
        mount_ask_api(app, AskApi(provider, lambda: HardwareProbe(archive).collect()))
        mount_profile_api(app, ProfileApi(ProfileVault(keys, enabled=True)))
        client = TestClient(app, base_url="http://127.0.0.1:8766")
        cli = {"Authorization": "Bearer " + token}
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
        origin = {"Origin": "http://127.0.0.1:8766"}
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
                    sentinel not in row[0] and hashlib.sha256(sentinel.encode()).hexdigest() not in row[0]
                    for row in rows
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
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "actual_os_store": True,
                    "actual_local_model": True,
                    "model_calls": 1,
                    "asgi_cookie_http": True,
                    "suppression_denied_before_inference": True,
                    "clear_profile_or_fingerprint_in_db": False,
                }
            )
        )
    finally:
        stop(daemon)


if __name__ == "__main__":
    main()
