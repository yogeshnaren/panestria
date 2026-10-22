"""Actual PG/crypto/HTTP publication; native model/key/capacity are explicit fixtures."""

from pathlib import Path

import psycopg
import pytest
from test_aos_009 import _client
from test_local_provider import transport, valid_frames
from test_profile_ask import ask_profile as ask_profile  # noqa: F401
from test_profile_style import styled as styled  # noqa: F401
from test_profile_vault import profile as profile  # noqa: F401

from panestria.api.main import mount_ask_api, mount_profile_api
from panestria.api.routes.ask import AskApi
from panestria.api.routes.profiles import ProfileApi
from panestria.inference.local import LocalProvider
from panestria.kernel.uow import UnitOfWork
from panestria.resources.hardware import HardwareProbe

ROOT = Path(__file__).resolve().parents[2]
CLI = {"Authorization": "Bearer test-only-cli-token-at-least-16"}
SOURCE = "Cost may be €1.25 [S1].\n\nLatency is unconfirmed at 42 ms [S2]."


@pytest.fixture
def r1_task(r1_migration_task):
    return r1_migration_task


def application(styled, task, enabled):
    _dsn, _actor, _handle, _keys, vault, _service, _request, _preferences = styled
    client = _client(task)
    frames = valid_frames()
    frames[0]["response"] = SOURCE
    mock, calls = transport(frames)
    provider = LocalProvider(Path("/synthetic"), transport=mock)
    mount_ask_api(
        client.app,
        AskApi(
            provider,
            lambda: HardwareProbe(ROOT / "docs/specification/attachments/agentos-skills-v0.1.0.zip").collect(
                preset="omen-8gb"
            ),
            lossless_presentation=enabled,
        ),
    )
    mount_profile_api(client.app, ProfileApi(vault))
    return client, calls, provider


@pytest.mark.parametrize("enabled", [False, True])
def test_explicit_presentation_saves_metadata_only_with_one_local_inference(styled, r1_task, enabled, record_property):
    dsn, _actor, _handle, _keys, _vault, _service, request, preferences = styled
    client, calls, _ = application(styled, r1_task, enabled)
    record_property("mode", "ACTUAL_PG_CRYPTO_HTTP__EXPLICIT_LOCAL_PROVIDER_KEY_CAPACITY_FIXTURES__NO_EXTRA_INFERENCE")
    response = client.post("/v2/ask", json=request.model_dump(mode="json"), headers=CLI)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["text"] == (
        "- Cost may be €1.25 [S1].\n\n- Latency is unconfirmed at 42 ms [S2]." if enabled else SOURCE
    )
    assert body["response_sha256"] is None and not body["response_retained"]
    assert body["privacy_label"] == "RESTRICTED"
    if enabled:
        observed = body["usage"]["presentation"]
        assert observed["state"] == "APPLIED" and observed["elapsed_seconds"] >= 0
        assert observed["input_bytes"] == len(SOURCE.encode()) and observed["output_bytes"] == len(
            body["text"].encode()
        )
        assert (
            observed["readability_quality"]
            == observed["factual_support"]
            == observed["owner_preference"]
            == "NOT_ASSESSED"
        )
        assert "formatting" not in observed and "language" not in observed
    else:
        assert "presentation" not in body["usage"]
    receipt = client.get(f"/v1/ask/{request.request_id}", headers=CLI).json()
    assert receipt["usage"] == body["usage"] and "text" not in receipt
    assert client.post("/v2/ask", json=request.model_dump(mode="json"), headers=CLI).json()["replayed_receipt"]
    assert sum(r.method == "POST" for r in calls) == 1 and {r.url.host for r in calls} == {"local-model"}
    with psycopg.connect(dsn) as c:
        for table in ("ask_request", "ask_profile_context", "context_pack", "learning_record"):
            rows = c.execute(f"SELECT row_to_json(t)::text FROM panestria.{table} t").fetchall()
            assert all(SOURCE not in row[0] and preferences.model_dump_json() not in row[0] for row in rows)


def test_withdrawal_after_model_return_blocks_layout_and_publication(styled, r1_task, monkeypatch):
    dsn, actor, handle, _keys, vault, _service, request, _preferences = styled
    client, calls, provider = application(styled, r1_task, True)
    generate = provider.agenerate

    async def return_then_withdraw(inference):
        result = await generate(inference)
        with psycopg.connect(dsn) as c:
            vault.suppress(UnitOfWork(c), actor, handle.profile_id, 1)
        return result

    monkeypatch.setattr(provider, "agenerate", return_then_withdraw)
    response = client.post("/v2/ask", json=request.model_dump(mode="json"), headers=CLI)
    assert response.status_code != 200 and SOURCE not in response.text
    receipt = client.get(f"/v1/ask/{request.request_id}", headers=CLI).json()
    assert receipt["state"] == "UNAVAILABLE" and receipt["response_sha256"] is None
    assert not receipt["usage"] or "presentation" not in receipt["usage"]
    assert sum(r.method == "POST" for r in calls) == 1
