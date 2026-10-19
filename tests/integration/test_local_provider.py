"""Local adapter contracts: no fallback, explicit deltas and honest terminal failures."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import httpx2 as httpx
import pytest

from panestria.contracts.inference import InferenceRequest, InferenceResult, InferenceUnavailable
from panestria.inference.local import InferenceDelta, LocalProvider
from panestria.inference.runtime import MODEL, MODEL_DIGEST


def request(**changes: object) -> InferenceRequest:
    body = dict(
        owner_id=str(uuid4()),
        project_id=str(uuid4()),
        request_id=str(uuid4()),
        model_ref=MODEL,
        prompt="Say READY",
        label="RESTRICTED",
        trace_id=uuid4().hex,
        deadline_seconds=1.0,
    )
    body.update(changes)
    return InferenceRequest.model_validate(body)


def transport(
    frames: list[dict[str, object]], *, pin: str = MODEL_DIGEST
) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    calls: list[httpx.Request] = []

    async def handle(r: httpx.Request) -> httpx.Response:
        calls.append(r)
        if r.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": MODEL, "digest": pin}]})
        if r.url.path == "/api/generate":
            return httpx.Response(200, content="\n".join(json.dumps(f) for f in frames))
        raise AssertionError("Unexpected endpoint")

    return httpx.MockTransport(handle), calls


def valid_frames() -> list[dict[str, object]]:
    return [
        {"model": MODEL, "response": "READY", "done": False},
        {"model": MODEL, "response": "", "done": True, "done_reason": "stop", "prompt_eval_count": 12, "eval_count": 2},
    ]


def test_local_only_stream_and_usage(record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-016-TC01")
    record_property("source_clauses", "AOS-016-F01,AOS-016-F04")
    mocked, calls = transport(valid_frames())
    provider = LocalProvider(Path("/synthetic/model.sock"), transport=mocked)

    async def collect() -> list[InferenceDelta | InferenceResult]:
        return [e async for e in provider.stream(request())]

    events = asyncio.run(collect())
    assert events[0] == InferenceDelta("READY") and isinstance(events[-1], InferenceResult)
    assert events[-1].text == "READY" and events[-1].first_token_seconds is not None
    assert events[-1].usage.cash_actual_microusd == 0 and events[-1].usage.quota_remaining is None
    body = json.loads(calls[-1].content)
    assert body["stream"] is True and body["options"]["num_ctx"] == 2048 and body["options"]["num_thread"] == 2
    assert {r.url.host for r in calls} == {"local-model"}
    with pytest.raises(InferenceUnavailable, match="embedding_model_not_configured"):
        asyncio.run(provider.embed("data"))


@pytest.mark.parametrize(
    "change,code",
    [
        ({"label": "UNKNOWN"}, "classification_required"),
        ({"model_ref": "absent-model"}, "model_not_pinned"),
        ({"context_tokens": 512, "prompt": "x" * 512}, "context_budget_exceeded"),
    ],
)
def test_local_rejects_before_http(change: dict[str, object], code: str) -> None:
    mocked, calls = transport(valid_frames())
    with pytest.raises(InferenceUnavailable, match=code):
        LocalProvider(Path("/synthetic"), transport=mocked).generate(request(**change))
    assert calls == []


def test_local_no_missing_model_fallback(record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-016-TC02")
    record_property("source_clauses", "AOS-016-F03,AOS-016-AC03")
    mocked, calls = transport(valid_frames(), pin="00" * 32)
    with pytest.raises(InferenceUnavailable, match="model_missing_or_digest_mismatch"):
        LocalProvider(Path("/synthetic"), transport=mocked).generate(request())
    assert len(calls) == 1 and calls[0].url.path == "/api/tags"


@pytest.mark.parametrize(
    "frames,code",
    [
        (valid_frames()[:1], "model_output_incomplete"),
        ([{"model": MODEL, "response": "claim", "done": True, "approved": True}], "model_stream_invalid"),
        ([{"model": "wrong", "response": "claim", "done": False}], "model_version_mismatch"),
        (valid_frames() + valid_frames()[:1], "model_stream_invalid"),
        ([valid_frames()[0], {**valid_frames()[1], "eval_count": 129}], "model_token_limit_exceeded"),
    ],
)
def test_local_incomplete_never_success(frames: list[dict[str, object]], code: str) -> None:
    mocked, _ = transport(frames)
    provider = LocalProvider(Path("/synthetic"), transport=mocked)
    with pytest.raises(InferenceUnavailable, match=code):
        provider.generate(request())
    assert provider.capacity.acquire(blocking=False)
    provider.capacity.release()


def test_absolute_timeout_and_cancel_release() -> None:
    async def slow(r: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200)

    provider = LocalProvider(Path("/synthetic"), transport=httpx.MockTransport(slow))
    with pytest.raises(InferenceUnavailable, match="model_timeout_or_response_unknown"):
        provider.generate(request(deadline_seconds=0.1))

    async def cancel() -> None:
        task = asyncio.create_task(provider.agenerate(request()))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert provider.capacity.acquire(blocking=False)
        provider.capacity.release()

    asyncio.run(cancel())


def test_structured_output_is_explicit_local_json_only() -> None:
    mocked, calls = transport(valid_frames())
    LocalProvider(Path("/synthetic"), transport=mocked, json_output=True).generate(request())
    assert json.loads(calls[-1].content)["format"] == "json"
    mocked, calls = transport(valid_frames())
    LocalProvider(Path("/synthetic"), transport=mocked).generate(request())
    assert "format" not in json.loads(calls[-1].content)
    with pytest.raises(ValueError, match="invalid_local_output_format"):
        LocalProvider(Path("/synthetic"), json_output="json")  # type: ignore[arg-type]
