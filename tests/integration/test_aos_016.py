"""SDK privacy, exact model and result/cost uncertainty contracts."""

from __future__ import annotations

import json
from decimal import Decimal
from uuid import uuid4

import httpx2 as httpx
import pytest
from pydantic import SecretStr, ValidationError

from panestria.contracts.inference import InferenceRequest, InferenceUnavailable
from panestria.inference.sdk_provider import SdkProvider, TokenTariff

MODEL = "gpt-5.4-nano-2026-03-17"


def _request(**changes: object) -> InferenceRequest:
    data = dict(
        owner_id=str(uuid4()),
        project_id=str(uuid4()),
        request_id=str(uuid4()),
        model_ref=MODEL,
        prompt="Return OK.",
        label="PUBLIC",
        offline=False,
        max_output_tokens=16,
        trace_id="ab" * 16,
    )
    data.update(changes)
    return InferenceRequest.model_validate(data)


class Permission:
    def __init__(self, allowed_hash: str) -> None:
        self.allowed_hash = allowed_hash
        self.calls = 0

    def require(self, request: InferenceRequest, provider: str, upper_cash_microusd: int) -> None:
        assert provider == "openai-api" and upper_cash_microusd < 1000
        if request.sha256() != self.allowed_hash:
            raise InferenceUnavailable("exact_request_not_approved")
        self.calls += 1


def _provider(request: InferenceRequest, handler: object) -> tuple[SdkProvider, Permission]:
    permission = Permission(request.sha256())
    tariff = TokenTariff(
        MODEL, Decimal("0.20"), Decimal("1.25"), "https://developers.openai.com/api/docs/models/gpt-5.4-nano"
    )
    return SdkProvider(
        SecretStr("unit-test-placeholder"), tariff, permission, transport=httpx.MockTransport(handler)
    ), permission


def test_sdk_privacy_and_exact_request() -> None:
    request = _request()
    seen = []

    def handle(http: httpx.Request) -> httpx.Response:
        seen.append(http)
        raise AssertionError("privacy denial must happen before HTTP")

    provider, permission = _provider(request, handle)
    try:
        for overrides in [dict(label="PRIVATE"), dict(label="RESTRICTED"), dict(label="UNKNOWN"), dict(offline=True)]:
            with pytest.raises(InferenceUnavailable, match="cloud_privacy_denied"):
                provider.generate(request.model_copy(update=overrides))
        with pytest.raises(InferenceUnavailable, match="exact_request_not_approved"):
            provider.generate(request.model_copy(update={"prompt": "different payload"}))
        with pytest.raises(InferenceUnavailable, match="model_not_pinned"):
            provider.generate(request.model_copy(update={"model_ref": "different-model"}))
        assert not seen and permission.calls == 0
        with pytest.raises(ValidationError):
            InferenceRequest.model_validate({**request.model_dump(), "approved": True})
    finally:
        provider.close()


def test_sdk_result_has_no_invented_cash_or_quota() -> None:
    request = _request()

    def handle(http: httpx.Request) -> httpx.Response:
        assert str(http.url) == "https://api.openai.com/v1/responses"
        body = json.loads(http.content)
        assert body["max_output_tokens"] == 16 and body["tools"] == [] and body["store"] is False
        return httpx.Response(
            200,
            json={
                "id": "response_test",
                "created_at": 1,
                "object": "response",
                "status": "completed",
                "error": None,
                "model": MODEL,
                "output": [
                    {
                        "type": "message",
                        "id": "message_test",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": "OK", "annotations": []}],
                    }
                ],
                "usage": {
                    "input_tokens": 20,
                    "output_tokens": 2,
                    "total_tokens": 22,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 0},
                },
            },
        )

    provider, _ = _provider(request, handle)
    try:
        result = provider.generate(request)
        assert result.text == "OK" and result.completion == "COMPLETED"
        assert result.usage.cash_actual_microusd is None and result.usage.quota_remaining is None
        assert result.usage.cash_estimate_microusd == 7
    finally:
        provider.close()


@pytest.mark.parametrize(
    "status,code",
    [(401, "provider_auth_required"), (429, "provider_quota_or_rate_limit"), (500, "provider_request_rejected")],
)
def test_sdk_errors_do_not_retry(status: int, code: str) -> None:
    request = _request()
    calls = []

    def handle(http: httpx.Request) -> httpx.Response:
        calls.append(http)
        return httpx.Response(status, json={"error": {"message": "synthetic secret sentinel", "type": "test"}})

    provider, _ = _provider(request, handle)
    try:
        with pytest.raises(InferenceUnavailable, match=code) as error:
            provider.generate(request)
        assert len(calls) == 1 and "synthetic secret sentinel" not in str(error.value)
    finally:
        provider.close()


def test_sdk_absolute_deadline_and_partial_output() -> None:
    import asyncio
    import time

    request = _request(deadline_seconds=0.1)

    async def slow(http: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        raise AssertionError("deadline must cancel transport")

    provider, _ = _provider(request, slow)
    began = time.monotonic()
    try:
        with pytest.raises(InferenceUnavailable, match="provider_response_unknown"):
            provider.generate(request)
        assert time.monotonic() - began < 1
    finally:
        provider.close()

    def partial(http: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "test_partial",
                "created_at": 1,
                "object": "response",
                "status": "incomplete",
                "error": None,
                "model": MODEL,
                "output": [],
                "incomplete_details": {"reason": "max_output_tokens"},
            },
        )

    request = _request()
    provider, _ = _provider(request, partial)
    try:
        with pytest.raises(InferenceUnavailable, match="provider_output_incomplete"):
            provider.generate(request)
    finally:
        provider.close()
