"""Real DB/loopback HTTP; model/process and inference are explicit CI fixtures."""

from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path
from uuid import uuid4

import httpx2 as httpx
import psycopg
import pytest
import uvicorn
from fastapi.testclient import TestClient
from test_local_provider import transport, valid_frames

from panestria.api import local_server
from panestria.api.local_protocol import LocalHttpProtocol
from panestria.config import Settings
from panestria.config_local import (
    LocalApplicationRejected,
    create_local_token,
    load_local_settings,
)
from panestria.contracts.inference import InferenceUnavailable
from panestria.inference.runtime import ModelRuntime
from panestria.kernel.errors import KernelDenied
from panestria.kernel.local_setup import LocalSetupIntent, LocalSetupService
from panestria.kernel.uow import UnitOfWork
from panestria.resources.hardware import HardwareProbe


def configuration(root, *, port=8766):
    token = root / "local-token"
    create_local_token(token)
    cache = root / "public-models"
    cache.mkdir()
    (cache / "blobs").mkdir()
    (cache / "manifests").mkdir()
    path = root / "local.json"
    body = {
        "schema_version": 1,
        "owner_id": str(uuid4()),
        "project_id": str(uuid4()),
        "bind_port": port,
        "token_file": str(token),
        "model_cache": str(cache),
        "runtime_directory": str(root / "runtime"),
    }
    path.write_text(json.dumps(body))
    path.chmod(0o600)
    return path, body


@pytest.mark.parametrize(
    "mutation",
    [
        {"schema_version": True},
        {"schema_version": 2},
        {"owner_id": "PRIVATE_SENTINEL"},
        {"bind_host": "0.0.0.0"},
        {"bind_host": "localhost"},
        {"bind_port": True},
        {"enable_profiles": True},
        {"provider": "anthropic-api"},
        {"workers": 2},
    ],
)
def test_configuration_rejects_authority_and_version_overrides(tmp_path, mutation):
    path, body = configuration(tmp_path)
    path.write_text(json.dumps({**body, **mutation}))
    with pytest.raises(LocalApplicationRejected, match="^invalid_local_configuration$") as exc:
        load_local_settings(path)
    assert "PRIVATE_SENTINEL" not in str(exc.value)


def test_configuration_and_token_are_private_and_never_overwritten(tmp_path):
    path, body = configuration(tmp_path)
    config, token = load_local_settings(path)
    assert token.get_secret_value() not in repr(token)
    original = config.token_file.read_bytes()
    with pytest.raises(LocalApplicationRejected, match="local_token_creation_denied"):
        create_local_token(config.token_file)
    assert config.token_file.read_bytes() == original
    config.token_file.chmod(0o640)
    with pytest.raises(LocalApplicationRejected, match="local_file_must_be_private"):
        load_local_settings(path)
    config.token_file.chmod(0o600)
    path.chmod(0o644)
    with pytest.raises(LocalApplicationRejected, match="local_file_must_be_private"):
        load_local_settings(path)
    path.chmod(0o600)
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(LocalApplicationRejected, match="local_file_unavailable"):
        load_local_settings(link)
    (config.model_cache / "private-not-model-data").write_text("SYNTHETIC_PRIVATE")
    with pytest.raises(LocalApplicationRejected, match="dedicated_model_cache_required"):
        load_local_settings(path)


def test_port_conflict_preserves_original_listener(tmp_path):
    with socket.socket() as original:
        original.bind(("127.0.0.1", 0))
        original.listen()
        path, _ = configuration(tmp_path, port=original.getsockname()[1])
        config, _ = load_local_settings(path)
        with pytest.raises(LocalApplicationRejected, match="local_bind_unavailable"):
            local_server.owned_listener(config)
        with socket.create_connection(("127.0.0.1", config.bind_port), timeout=1):
            pass


def test_preserve_existing_runtime_never_inspects_or_reaps_a_container(tmp_path, monkeypatch):
    runtime = ModelRuntime(tmp_path / "models", tmp_path / "socket", preserve_existing=True)
    calls = []

    def docker(args):
        calls.append(args)
        return "preexisting-controller\n"

    monkeypatch.setattr(runtime, "_docker", docker)
    with pytest.raises(InferenceUnavailable, match="existing_model_service_preserved"):
        runtime._reap_orphans()
    assert calls == [["ps", "-a", "-q", "--filter", "label=panestria.purpose=local-model"]]


class ModelFixture(ModelRuntime):
    """No Docker/model in default CI; actual runtime is a separate live test."""

    def start(self):
        self.started_fixture = True
        self.socket_directory.mkdir(mode=0o700)
        self.fixture_socket = socket.socket(socket.AF_UNIX)
        self.fixture_socket.bind(str(self.socket_path))

    def stop(self):
        self.stopped_fixture = True
        if hasattr(self, "fixture_socket"):
            self.fixture_socket.close()
            self.socket_path.unlink(missing_ok=True)


@pytest.fixture
def configured(r1_database, tmp_path, monkeypatch):
    path, _ = configuration(tmp_path)
    config, token = load_local_settings(path)
    intent = LocalSetupIntent(owner_id=config.owner_id, project_id=config.project_id, intent="OFFLINE_ASK")
    with psycopg.connect(r1_database) as c:
        LocalSetupService().initialize(UnitOfWork(c), intent)
    monkeypatch.setattr(local_server, "ModelRuntime", ModelFixture)
    archive = Path(__file__).resolve().parents[2] / "docs/specification/attachments/agentos-skills-v0.1.0.zip"
    manifest = HardwareProbe(archive).collect(preset="omen-8gb")
    monkeypatch.setattr(local_server.HardwareProbe, "collect", lambda self: manifest)
    settings = Settings(database_url=r1_database).validate_profile()
    app = local_server.build_local_app(config, settings, token.get_secret_value())
    mocked, calls = transport(valid_frames())
    app.state.ask_api.provider.transport = mocked
    return config, token.get_secret_value(), settings, app, calls


def test_local_lifespan_scope_no_build_routes_and_shutdown(configured):
    config, token, settings, app, calls = configured
    with TestClient(app, base_url=config.origin) as client:
        cli = {"Authorization": "Bearer " + token}
        assert client.get("/v1/local/status").status_code == 401
        body = client.get("/v1/local/status", headers=cli).json()
        assert body["model_socket_present"] and body["profiles"] == "DISABLED"
        assert body["runtime_certified"] is False and body["release_gate"] == "NOT_EVALUATED"
        assert client.post("/v1/goals", json={}, headers=cli).status_code == 404
        assert client.post("/v2/profiles", json={}, headers=cli).status_code == 404
        assert client.post("/v2/ask", json={}, headers=cli).json()["code"] == "profile_not_configured"
        code = client.post("/v1/session/code", json={}, headers=cli).json()["code"]
        origin = {"Origin": config.origin}
        paired = client.post("/v1/session/pair", json={"code": code}, headers=origin)
        csrf = paired.json()["csrf_token"]
        request = {"request_id": str(uuid4()), "project_id": str(config.project_id), "question": "Say READY"}
        assert client.post("/v1/ask", json=request, headers=origin).status_code == 403 and not calls
        headers = {**origin, "X-Panestria-CSRF": csrf}
        result = client.post("/v1/ask", json=request, headers=headers)
        assert result.status_code == 200 and result.json()["text"] == "READY"
        assert client.post("/v1/ask", json=request, headers=headers).json()["replayed_receipt"]
        assert client.post("/v1/session/logout", json={}, headers=headers).status_code == 200
    assert app.state.local_model.stopped_fixture and not app.state.local_model.socket_path.exists()
    assert app.state.ask_api.governor.stopped


def test_unconfigured_policy_stops_before_model_start(configured):
    config, token, settings, app, calls = configured
    with psycopg.connect(settings.database_url.get_secret_value()) as c:
        # Deliberately alter only synthetic current pointer; immutable history stays.
        c.execute("UPDATE panestria.project SET policy_version=0 WHERE id=%s", (str(config.project_id),))
    with pytest.raises(KernelDenied, match="policy_unconfigured"), TestClient(app):
        pass
    assert not hasattr(app.state.local_model, "started_fixture")
    assert app.state.local_model.stopped_fixture and not calls


def test_real_http_enforces_headers_and_slow_header_deadline(configured, monkeypatch):
    config, token, settings, app, _ = configured
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    # Rebuild at the actual private listener's origin; DB identity stays unchanged.
    config = config.model_copy(update={"bind_port": port})
    app.state.health.shutdown()
    app = local_server.build_local_app(config, settings, token)
    monkeypatch.setattr(LocalHttpProtocol, "header_deadline_seconds", 0.15)
    server = uvicorn.Server(local_server.server_config(app))
    worker = threading.Thread(target=server.run, kwargs={"sockets": [listener]})
    worker.start()
    try:
        deadline = time.monotonic() + 5
        while not server.started:
            assert worker.is_alive() and time.monotonic() < deadline, "fixture_server_not_started"
            time.sleep(0.02)
        with httpx.Client(base_url=config.origin, trust_env=False, timeout=2) as client:
            assert client.get("/healthz").status_code == 200
            assert client.get("/healthz", headers={"Host": "attacker.invalid"}).status_code == 403
            assert client.get("/healthz?token=SYNTHETIC_PRIVATE").status_code == 400
            assert (
                client.post("/v1/ask", content="x" * 65537, headers={"Content-Type": "application/json"}).status_code
                == 413
            )
            assert client.get("/healthz", headers={"Origin": "http://attacker.invalid"}).status_code == 403
        with socket.create_connection(("127.0.0.1", port), timeout=2) as slow:
            slow.sendall(b"GET /healthz HTTP/1.1\r\nHost: ")
            assert slow.recv(1) == b""
        with socket.create_connection(("127.0.0.1", port), timeout=2) as keepalive:
            keepalive.sendall(f"GET /healthz HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n\r\n".encode())
            assert b"200 OK" in keepalive.recv(8192)
            keepalive.sendall(b"GET /healthz HTTP/1.1\r\nHost: ")
            # Drain first response body if TCP split it, then observe closed headers.
            while keepalive.recv(8192):
                pass
    finally:
        server.should_exit = True
        worker.join(timeout=8)
        listener.close()
        assert not worker.is_alive() and app.state.local_model.stopped_fixture
