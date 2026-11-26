"""``panestria serve`` runs the owner app on real PostgreSQL and a real loopback port.

The model and inference are CI fixtures, as in ``test_local_server.py``: the
model "starts" by binding its socket, and Ask answers through a mock transport.
The Build run service is a stand-in, as in ``test_owner_sessions.py``; only its
presence and review root are used.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx2 as httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient
from test_ask_policy import apply, build_policy, current, offline
from test_local_provider import transport, valid_frames
from test_local_server import ModelFixture, configuration
from test_owner_sessions import _StubRun
from typer.testing import CliRunner

from panestria.api import local_server, owner
from panestria.api.app import build_app
from panestria.api.local_protocol import AnsweringHttpProtocol
from panestria.api.owner import owner_profile, serve_owner
from panestria.assets import AssetUnavailable
from panestria.cli.main import app as cli
from panestria.config import Settings
from panestria.config_local import LocalApplicationRejected, LocalApplicationSettings, load_local_settings
from panestria.kernel.errors import KernelDenied
from panestria.resources.hardware import HardwareProbe


@dataclass
class Owner:
    path: Path
    config: LocalApplicationSettings
    token: str
    assets: Path
    build: Path
    task: dict[str, str]

    def app(self, *, build: bool = False) -> Any:
        settings = Settings(database_url=self.task["dsn"]).validate_profile()
        profile = owner_profile(self.config, settings, self.token, self.assets, build_run=self.build if build else None)
        application = build_app(profile)
        application.state.ask_api.provider.transport = transport(valid_frames())[0]
        return application


@pytest.fixture
def owner_setup(r1_task: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Owner:
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    path, body = configuration(tmp_path, port=port)
    # The seeded task's project, so a policy review can be proposed against it.
    path.write_text(json.dumps({**body, "owner_id": r1_task["owner"], "project_id": r1_task["project"]}))
    config, token = load_local_settings(path)
    offline(r1_task)
    monkeypatch.setattr(local_server, "ModelRuntime", ModelFixture)
    archive = Path(__file__).resolve().parents[2] / "docs/specification/attachments/agentos-skills-v0.1.0.zip"
    manifest = HardwareProbe(archive).collect(preset="omen-8gb")
    monkeypatch.setattr(local_server.HardwareProbe, "collect_cpu", lambda self: manifest)
    review = tmp_path / "review"
    (review / "reports").mkdir(parents=True, mode=0o700)
    review.chmod(0o700)
    _StubRun.root = review
    monkeypatch.setattr("panestria.execution.mission_run.MissionRunService", _StubRun)
    monkeypatch.setattr("panestria.api.routes.mission_run.MissionRunService", _StubRun)
    assets = tmp_path / "assets"
    assets.mkdir(mode=0o700)
    for name, content in (("index.html", b'<div id="root"></div>'), ("mission.js", b";"), ("mission.css", b"*{}")):
        (assets / name).write_bytes(content)
    return Owner(path, config, token.get_secret_value(), assets, tmp_path / "build.json", r1_task)


def _ask(client: TestClient, owner: Owner) -> Any:
    request = {"request_id": str(uuid4()), "project_id": str(owner.config.project_id), "question": "Say READY"}
    return client.post("/v1/ask", json=request, headers={"Authorization": "Bearer " + owner.token})


def test_the_owner_app_starts_its_model_and_serves_ask_to_the_cli(owner_setup: Owner) -> None:
    app = owner_setup.app()
    bearer = {"Authorization": "Bearer " + owner_setup.token}
    with TestClient(app, base_url=owner_setup.config.origin) as client:
        assert app.state.local_model.started_fixture
        status = client.get("/v1/local/status", headers=bearer).json()
        assert status["policy_ref"].startswith("project-policy:1:") and status["trust_profile"] == "SYNTHETIC_DEV"
        answer = _ask(client, owner_setup)
        assert answer.status_code == 200 and answer.json()["text"] == "READY"
        # The R0 goal, approval and artifact routes are not part of the owner app.
        for method, path in (("POST", "/v1/goals"), ("GET", "/v1/approvals"), ("GET", f"/v1/artifacts/{uuid4()}")):
            body = {} if method == "POST" else None
            assert client.request(method, path, headers=bearer, json=body).status_code == 404, path
    assert app.state.local_model.stopped_fixture and not app.state.local_model.socket_path.exists()


def test_ask_still_starts_after_build_setup_applies_its_policy(owner_setup: Owner) -> None:
    actor = offline(owner_setup.task)
    apply(owner_setup.task, actor, build_policy(current(owner_setup.task, actor)))
    # The single-mode Ask server keeps the strict check and never starts its model.
    settings = Settings(database_url=owner_setup.task["dsn"]).validate_profile()
    single = local_server.build_local_app(owner_setup.config, settings, owner_setup.token)
    with pytest.raises(KernelDenied, match="^local_setup_policy_conflict$"), TestClient(single):
        pass
    assert not hasattr(single.state.local_model, "started_fixture")
    app = owner_setup.app(build=True)
    with TestClient(app, base_url=owner_setup.config.origin) as client:
        status = client.get("/v1/local/status", headers={"Authorization": "Bearer " + owner_setup.token}).json()
        assert status["policy_ref"].startswith("project-policy:2:") and status["trust_profile"] == "PERSONAL_SANDBOX"
        assert _ask(client, owner_setup).json()["text"] == "READY"


class _Recorded(uvicorn.Server):
    """The real server; records each instance so the test can stop it."""

    instances: list[_Recorded] = []

    def __init__(self, config: uvicorn.Config) -> None:
        super().__init__(config)
        _Recorded.instances.append(self)


@dataclass
class Served:
    owner: Owner
    server: uvicorn.Server
    announced: dict[str, Any]


@pytest.fixture
def served(owner_setup: Owner, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]) -> Iterator[Served]:
    monkeypatch.setenv("PANESTRIA_DATABASE_URL", owner_setup.task["dsn"])
    monkeypatch.setattr(AnsweringHttpProtocol, "header_deadline_seconds", 0.2)
    monkeypatch.setattr(uvicorn, "Server", _Recorded)
    _Recorded.instances = []
    failures: list[BaseException] = []

    def run() -> None:
        try:
            serve_owner(owner_setup.path, build_run=owner_setup.build, assets=owner_setup.assets)
        except BaseException as exc:  # Reported by the test below.
            failures.append(exc)

    worker = threading.Thread(target=run)
    worker.start()
    deadline = time.monotonic() + 10
    while not (_Recorded.instances and _Recorded.instances[0].started):
        assert worker.is_alive() and time.monotonic() < deadline, failures or "owner_server_not_started"
        time.sleep(0.02)
    server = _Recorded.instances[0]
    announced = json.loads(capfd.readouterr().out.strip().splitlines()[-1])
    try:
        yield Served(owner_setup, server, announced)
    finally:
        server.should_exit = True
        worker.join(timeout=10)
        assert not worker.is_alive() and not failures, failures
    app = server.config.app
    assert app.state.local_model.stopped_fixture and not app.state.local_model.socket_path.exists()
    released(owner_setup.config.bind_port)


def released(port: int) -> None:
    """No socket listens on ``port`` any more (connections in TIME_WAIT do not count)."""
    with socket.socket() as again:
        again.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        again.bind(("127.0.0.1", port))
        again.listen()


def _pair(owner: Owner, scope: str) -> dict[str, Any]:
    result = CliRunner().invoke(cli, ["pair-code", "--config", str(owner.path), "--scope", scope])
    assert result.exit_code == 0, result.output
    issued = json.loads(result.output)
    assert issued["scope"] == scope and issued["origin"] == owner.config.origin and owner.token not in result.output
    with httpx.Client(base_url=owner.config.origin, trust_env=False, timeout=5) as client:
        origin = {"Origin": owner.config.origin}
        paired = client.post(f"/v1/session/{scope}/pair", json={"code": issued["code"]}, headers=origin)
    assert paired.status_code == 200, paired.text
    return {"cookie": paired.headers["set-cookie"], **paired.json()}


def test_serve_runs_the_owner_app_on_its_port_with_one_transport_behaviour(served: Served) -> None:
    owner_setup = served.owner
    port = owner_setup.config.bind_port
    assert served.announced == {
        "schema_version": 1,
        "status": "STARTING",
        "origin": owner_setup.config.origin,
        "session_scopes": ["activity", "ask", "build"],
    }
    with httpx.Client(base_url=owner_setup.config.origin, trust_env=False, timeout=5) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/").text == '<div id="root"></div>'
    # An oversized declared body is refused before any body byte is read.
    oversized = raw(port, f"POST /v1/ask HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nContent-Length: 65537\r\n\r\n")
    assert oversized.startswith(b"HTTP/1.1 413 ") and b'"code":"body_too_large"' in oversized
    # A stalled header block is answered with 408, as the goal API always has been.
    stalled = raw(port, "GET /healthz HTTP/1.1\r\nHost: ")
    assert stalled.startswith(b"HTTP/1.1 408 ") and b'"code":"request_deadline_exceeded"' in stalled


def raw(port: int, request: str) -> bytes:
    """Send ``request`` as is and read until the server closes the connection."""
    with socket.create_connection(("127.0.0.1", port), timeout=5) as connection:
        connection.sendall(request.encode())
        reply = b""
        while chunk := connection.recv(4096):
            reply += chunk
    return reply


def test_pair_code_pairs_one_scope_and_a_build_session_lasts_an_hour(served: Served) -> None:
    owner_setup = served.owner
    for scope, seconds in (("build", 3600), ("ask", 8 * 3600), ("activity", 8 * 3600)):
        session = _pair(owner_setup, scope)
        assert f"panestria_owner_{scope}_" in session["cookie"] and f"Max-Age={seconds}" in session["cookie"]
        remaining = (datetime.fromisoformat(session["expires_at"]) - datetime.now(UTC)).total_seconds()
        assert seconds - 60 < remaining <= seconds, scope
    refused = CliRunner().invoke(cli, ["pair-code", "--config", str(owner_setup.path), "--scope", "root"])
    assert refused.exit_code == 2


def test_serve_without_a_dashboard_build_refuses_and_releases_the_port(
    owner_setup: Owner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PANESTRIA_DATABASE_URL", owner_setup.task["dsn"])

    def unpackaged() -> Path:
        raise AssetUnavailable("packaged_asset_missing")

    monkeypatch.setattr(owner, "mission_control", unpackaged)
    result = CliRunner().invoke(cli, ["serve", "--config", str(owner_setup.path)])
    assert (result.exit_code, json.loads(result.output)) == (2, {"code": "mission_build_required"})
    with pytest.raises(LocalApplicationRejected, match="^mission_build_required$"):
        serve_owner(owner_setup.path, assets=owner_setup.path.parent / "no-such-build")
    released(owner_setup.config.bind_port)
