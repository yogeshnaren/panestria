"""Actual HTTP authentication/receipts while provider traffic is hermetic and local."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from test_aos_009 import _client
from test_ask_kernel import initialize
from test_local_provider import transport, valid_frames

from panestria.api.main import mount_ask_api
from panestria.api.routes.ask import AskApi
from panestria.inference.local import LocalProvider
from panestria.resources.hardware import HardwareProbe

ARCHIVE = Path(__file__).resolve().parents[2] / "docs/specification/attachments/agentos-skills-v0.1.0.zip"
CLI = {"Authorization": "Bearer test-only-cli-token-at-least-16"}


def test_http_ask_receipts_and_closed_authority(r1_task: dict[str, str], tmp_path: Path) -> None:
    actor, _ = initialize(r1_task, tmp_path)
    mocked, calls = transport(valid_frames())
    client = _client(r1_task)
    mount_ask_api(
        client.app,
        AskApi(
            LocalProvider(Path("/synthetic"), transport=mocked),
            lambda: HardwareProbe(ARCHIVE).collect(preset="omen-8gb"),
        ),
    )
    payload = dict(request_id=str(uuid4()), project_id=actor.project_id, question="Say READY")
    for extra in [{"offline": False}, {"approved": True}, {"retain_response": True}]:
        denied = client.post("/v1/ask", json={**payload, **extra}, headers=CLI)
        assert denied.status_code == 422
    assert calls == []
    answer = client.post("/v1/ask", json=payload, headers=CLI)
    assert answer.status_code == 200, answer.text
    assert answer.json()["text"] == "READY" and answer.json()["state"] == "COMPLETED"
    assert answer.json()["response_retained"] is False and answer.json()["offline"] is True
    replay = client.post("/v1/ask", json=payload, headers=CLI)
    assert replay.status_code == 200 and "text" not in replay.json() and replay.json()["replayed_receipt"]
    assert len(calls) == 2
    receipt = client.get(f"/v1/ask/{payload['request_id']}", headers=CLI)
    assert receipt.status_code == 200 and "text" not in receipt.json()
    conflict = client.post("/v1/ask", json={**payload, "question": "changed"}, headers=CLI)
    assert conflict.status_code == 409
    assert (
        client.post(
            "/v1/ask", json={**payload, "request_id": str(uuid4()), "project_id": str(uuid4())}, headers=CLI
        ).status_code
        == 404
    )
    assert (
        client.post(f"/v1/ask/{payload['request_id']}/cancel", json={"approve": True}, headers=CLI).status_code == 422
    )
    assert client.post(f"/v1/ask/{payload['request_id']}/cancel", json={}, headers=CLI).json()["state"] == "COMPLETED"


def test_http_browser_requires_csrf_before_inference(r1_task: dict[str, str], tmp_path: Path) -> None:
    actor, _ = initialize(r1_task, tmp_path)
    mocked, calls = transport(valid_frames())
    client = _client(r1_task)
    mount_ask_api(
        client.app,
        AskApi(
            LocalProvider(Path("/synthetic"), transport=mocked),
            lambda: HardwareProbe(ARCHIVE).collect(preset="omen-8gb"),
        ),
    )
    code = client.post("/v1/session/code", json={}, headers=CLI).json()["code"]
    origin = {"Origin": "http://127.0.0.1:8766"}
    paired = client.post("/v1/session/pair", json={"code": code}, headers=origin)
    csrf = paired.json()["csrf_token"]
    payload = dict(request_id=str(uuid4()), project_id=actor.project_id, question="Say READY")
    assert client.post("/v1/ask", json=payload, headers=origin).status_code == 403
    assert calls == []
    answer = client.post("/v1/ask", json=payload, headers={**origin, "X-Panestria-CSRF": csrf})
    assert answer.status_code == 200 and answer.json()["text"] == "READY"
    assert client.post("/v1/session/logout", json={}, headers={**origin, "X-Panestria-CSRF": csrf}).status_code == 200
    assert client.post("/v1/ask", json={**payload, "request_id": str(uuid4())}, headers=origin).status_code == 403
