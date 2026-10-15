"""HTTP orchestration uses mock local inference; never claim live model proof."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from test_aos_009 import _client
from test_local_provider import transport, valid_frames
from test_profile_ask import SENTINEL, ask_profile  # noqa: F401
from test_profile_vault import profile  # noqa: F401

from panestria.api.main import mount_ask_api, mount_profile_api
from panestria.api.routes.ask import AskApi
from panestria.api.routes.profiles import ProfileApi
from panestria.inference.local import LocalProvider
from panestria.resources.hardware import HardwareProbe, ProbeUnavailable

ROOT = Path(__file__).resolve().parents[2]
CLI = {"Authorization": "Bearer test-only-cli-token-at-least-16"}
ORIGIN = {"Origin": "http://127.0.0.1:8766"}


@pytest.fixture
def profile_http(ask_profile, r1_task):  # noqa: F811
    dsn, actor, handle, keys, vault, service, request = ask_profile
    client = _client(r1_task)
    frames = valid_frames()
    frames[0]["response"] = SENTINEL
    mocked, calls = transport(frames)
    mount_ask_api(
        client.app,
        AskApi(
            LocalProvider(Path("/synthetic"), transport=mocked),
            lambda: HardwareProbe(ROOT / "docs/specification/attachments/agentos-skills-v0.1.0.zip").collect(
                preset="omen-8gb"
            ),
        ),
    )
    mount_profile_api(client.app, ProfileApi(vault))
    return client, calls, keys, vault, request, frames


def test_http_profile_ask_receipt_replay_and_v1_compatibility(profile_http):
    client, calls, keys, vault, request, frames = profile_http
    payload = request.model_dump(mode="json")
    result = client.post("/v2/ask", json=payload, headers=CLI)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["schema_version"] == 2 and body["text"] == SENTINEL
    assert body["privacy_label"] == "RESTRICTED" and body["response_sha256"] is None
    assert body["response_digest_mode"] == "OMITTED_RESTRICTED_PROFILE"
    assert result.headers["cache-control"] == "no-store"
    generated = json.loads(calls[-1].content)
    assert SENTINEL in generated["prompt"] and {call.url.host for call in calls} == {"local-model"}
    assert len(calls) == 2
    receipt = client.get(f"/v1/ask/{request.request_id}", headers=CLI)
    assert receipt.status_code == 200 and SENTINEL not in receipt.text and "text" not in receipt.json()
    replay = client.post("/v2/ask", json=payload, headers=CLI)
    assert replay.status_code == 200 and "text" not in replay.json() and len(calls) == 2
    assert replay.json()["schema_version"] == 2
    frames[0]["response"] = "READY"
    ordinary = {"request_id": str(uuid4()), "project_id": request.project_id, "question": "Ordinary request"}
    previous = client.post("/v1/ask", json=ordinary, headers=CLI)
    assert previous.status_code == 200 and previous.json()["response_sha256"] is not None
    assert "response_digest_mode" not in previous.json()


def test_browser_csrf_disabled_and_stale_profile_deny_before_inference(profile_http):
    client, calls, keys, vault, request, frames = profile_http
    code = client.post("/v1/session/code", json={}, headers=CLI).json()["code"]
    paired = client.post("/v1/session/pair", json={"code": code}, headers=ORIGIN)
    headers = {**ORIGIN, "X-Panestria-CSRF": paired.json()["csrf_token"]}
    payload = request.model_dump(mode="json")
    assert client.post("/v2/ask", json=payload, headers=ORIGIN).status_code == 403
    vault.enabled = False
    denied = client.post("/v2/ask", json=payload, headers=headers)
    assert denied.json()["code"] == "profile_disabled" and calls == []
    vault.enabled = True
    payload["profile"]["expected_row_version"] = 10
    assert client.post("/v2/ask", json=payload, headers=headers).json()["code"] == "version_conflict"
    assert calls == []


def test_v2_shape_and_scope_cannot_expand_permission(profile_http):
    client, calls, keys, vault, request, frames = profile_http
    payload = request.model_dump(mode="json")
    for update in (
        {"privacy_label": "PUBLIC"},
        {"offline": False},
        {"response_digest_mode": "SHA256"},
        {"schema_version": 2.0},
    ):
        assert client.post("/v2/ask", json={**payload, **update}, headers=CLI).status_code == 422
    other = {**payload, "project_id": str(uuid4())}
    assert client.post("/v2/ask", json=other, headers=CLI).status_code == 404
    assert client.post("/v1/ask", json=payload, headers=CLI).status_code == 422
    assert calls == []


def test_resource_probe_failure_records_unavailable_without_inference(profile_http):
    client, calls, keys, vault, request, frames = profile_http

    def unavailable():
        raise ProbeUnavailable("synthetic_probe_denial")

    client.app.state.ask_api.probe = unavailable
    response = client.post("/v2/ask", json=request.model_dump(mode="json"), headers=CLI)
    assert response.status_code == 503 and calls == []
    receipt = client.get(f"/v1/ask/{request.request_id}", headers=CLI).json()
    assert receipt["state"] == "UNAVAILABLE" and receipt["response_sha256"] is None
