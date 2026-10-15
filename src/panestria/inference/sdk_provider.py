"""Explicit OpenAI SDK calls: no retries, redirects, inherited proxies or local fallback."""

from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass
from decimal import Decimal

import httpx2 as httpx
import openai
from pydantic import SecretStr

from panestria.contracts.classification import resolve_classification
from panestria.contracts.inference import (
    CloudAuthorizer,
    InferenceRequest,
    InferenceResult,
    InferenceUnavailable,
    Usage,
)


@dataclass(frozen=True)
class TokenTariff:
    model_ref: str
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    source_url: str

    def upper_bound(self, request: InferenceRequest) -> int:
        # Text tokenization is conservatively bounded by input bytes plus framing.
        # No tools, attachments, history or server-managed conversation are sent.
        input_ceiling = len(request.prompt.encode()) + 1024
        total = input_ceiling * self.input_usd_per_million + request.max_output_tokens * self.output_usd_per_million
        return math.ceil(total * Decimal("1.5"))

    def estimate(self, input_tokens: int, output_tokens: int) -> int:
        return math.ceil(input_tokens * self.input_usd_per_million + output_tokens * self.output_usd_per_million)


class SdkProvider:
    def __init__(
        self,
        credential: SecretStr,
        tariff: TokenTariff,
        authorizer: CloudAuthorizer,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not credential.get_secret_value():
            raise InferenceUnavailable("credential_missing")
        if (
            not tariff.input_usd_per_million.is_finite()
            or not tariff.output_usd_per_million.is_finite()
            or min(tariff.input_usd_per_million, tariff.output_usd_per_million) < 0
        ):
            raise InferenceUnavailable("pricing_unknown")
        self.tariff, self.authorizer = tariff, authorizer
        self._credential, self._transport = credential, transport

    def close(self) -> None:
        # Each request owns and closes its client, including cancellation paths.
        pass

    def generate(self, request: InferenceRequest) -> InferenceResult:
        return asyncio.run(self.agenerate(request))

    async def agenerate(self, request: InferenceRequest) -> InferenceResult:
        if request.offline or resolve_classification(request.label).effective in {None, "RESTRICTED"}:
            raise InferenceUnavailable("cloud_privacy_denied")
        if request.model_ref != self.tariff.model_ref:
            raise InferenceUnavailable("model_not_pinned")
        ceiling = self.tariff.upper_bound(request)
        self.authorizer.require(request, "openai-api", ceiling)
        began = time.monotonic()
        http = httpx.AsyncClient(
            transport=self._transport, follow_redirects=False, trust_env=False, timeout=request.deadline_seconds
        )
        client = openai.AsyncOpenAI(
            api_key=self._credential.get_secret_value(),
            base_url="https://api.openai.com/v1",
            max_retries=0,
            http_client=http,
        )
        try:
            async with client, asyncio.timeout(request.deadline_seconds):
                response = await client.responses.create(
                    model=request.model_ref,
                    input=request.prompt,
                    instructions="Answer the bounded request. Do not perform any action or request tools.",
                    max_output_tokens=request.max_output_tokens,
                    tools=[],
                    store=False,
                    reasoning={"effort": "none"},
                    service_tier="default",
                    timeout=request.deadline_seconds,
                )
        except TimeoutError:
            raise InferenceUnavailable("provider_response_unknown") from None
        except openai.AuthenticationError:
            raise InferenceUnavailable("provider_auth_required") from None
        except openai.RateLimitError:
            raise InferenceUnavailable("provider_quota_or_rate_limit") from None
        except openai.APIConnectionError:
            # The request may have reached the provider: reservation must remain unknown.
            raise InferenceUnavailable("provider_response_unknown") from None
        except openai.APIStatusError:
            raise InferenceUnavailable("provider_request_rejected") from None
        if response.status != "completed" or response.error is not None:
            raise InferenceUnavailable("provider_output_incomplete")
        if response.model != request.model_ref:
            raise InferenceUnavailable("model_version_mismatch")
        if not response.output_text or len(response.output_text.encode()) > 1024 * 1024:
            raise InferenceUnavailable("provider_output_invalid")
        usage = response.usage
        if usage is None:
            measured = Usage(None, None)
        else:
            counts = (usage.input_tokens, usage.output_tokens)
            if any(type(value) is not int or value < 0 for value in counts):
                raise InferenceUnavailable("provider_usage_invalid")
            if (
                usage.output_tokens > request.max_output_tokens
                or usage.input_tokens > len(request.prompt.encode()) + 1024
            ):
                raise InferenceUnavailable("provider_token_limit_exceeded")
            estimate = self.tariff.estimate(*counts)
            if estimate > ceiling:
                raise InferenceUnavailable("provider_usage_exceeded_reservation")
            measured = Usage(*counts, cash_estimate_microusd=estimate)
        return InferenceResult(response.model, response.output_text, measured, time.monotonic() - began, None)
