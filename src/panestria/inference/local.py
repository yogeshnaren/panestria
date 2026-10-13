"""Pinned local streaming; a terminal frame is required and no cloud adapter is reachable."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from threading import BoundedSemaphore
from typing import Any

import httpx2 as httpx

from panestria.contracts.inference import InferenceRequest, InferenceResult, InferenceUnavailable, Usage
from panestria.inference.runtime import MODEL, MODEL_DIGEST


@dataclass(frozen=True)
class InferenceDelta:
    text: str


class LocalProvider:
    capabilities = ("chat", "generate", "stream")

    def __init__(
        self, socket_path: Path, *, gpu: bool = False, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.socket_path, self.gpu, self.transport = socket_path, gpu, transport
        self.capacity = BoundedSemaphore(1)

    def _client(self, deadline: float) -> httpx.AsyncClient:
        transport = self.transport or httpx.AsyncHTTPTransport(uds=str(self.socket_path), retries=0, trust_env=False)
        return httpx.AsyncClient(
            base_url="http://local-model",
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            timeout=deadline,
        )

    def generate(self, request: InferenceRequest) -> InferenceResult:
        return asyncio.run(self.agenerate(request))

    async def agenerate(self, request: InferenceRequest) -> InferenceResult:
        terminal = None
        async for event in self.stream(request):
            if isinstance(event, InferenceResult):
                terminal = event
        if terminal is None:
            raise InferenceUnavailable("model_output_incomplete")
        return terminal

    async def _pinned(self, client: httpx.AsyncClient) -> None:
        tags = await client.get("/api/tags")
        if tags.status_code != 200 or len(tags.content) > 65536:
            raise InferenceUnavailable("model_catalog_unavailable")
        body = tags.json()
        if not isinstance(body, dict) or not isinstance(body.get("models"), list):
            raise InferenceUnavailable("model_catalog_invalid")
        if not any(m.get("name") == MODEL and m.get("digest") == MODEL_DIGEST for m in body["models"]):
            raise InferenceUnavailable("model_missing_or_digest_mismatch")

    async def stream(self, request: InferenceRequest) -> AsyncIterator[InferenceDelta | InferenceResult]:
        if request.model_ref != MODEL:
            raise InferenceUnavailable("model_not_pinned")
        if request.label == "UNKNOWN":
            raise InferenceUnavailable("classification_required")
        if len(request.prompt.encode()) + request.max_output_tokens + 128 > request.context_tokens:
            raise InferenceUnavailable("context_budget_exceeded")
        if not self.capacity.acquire(blocking=False):
            raise InferenceUnavailable("model_capacity")
        began, first = time.monotonic(), None
        text, terminal = "", None
        try:
            async with self._client(request.deadline_seconds) as client, asyncio.timeout(request.deadline_seconds):
                await self._pinned(client)
                async with client.stream(
                    "POST",
                    "/api/generate",
                    json={
                        "model": MODEL,
                        "prompt": request.prompt,
                        "stream": True,
                        "keep_alive": "5m",
                        "options": {
                            "num_ctx": request.context_tokens,
                            "num_predict": request.max_output_tokens,
                            "temperature": 0,
                            "seed": 7,
                            "num_thread": 2,
                            "num_gpu": -1 if self.gpu else 0,
                        },
                    },
                ) as response:
                    if response.status_code == 429:
                        raise InferenceUnavailable("model_capacity")
                    if response.status_code != 200:
                        raise InferenceUnavailable("model_request_rejected")
                    total = 0
                    async for line in response.aiter_lines():
                        total += len(line.encode())
                        if total > 1024 * 1024 or len(line.encode()) > 65536 or terminal is not None:
                            raise InferenceUnavailable("model_stream_invalid")
                        frame = json.loads(line)
                        allowed = {
                            "model",
                            "created_at",
                            "response",
                            "done",
                            "done_reason",
                            "context",
                            "error",
                            "total_duration",
                            "load_duration",
                            "prompt_eval_count",
                            "prompt_eval_duration",
                            "eval_count",
                            "eval_duration",
                        }
                        if not isinstance(frame, dict) or set(frame) - allowed:
                            raise InferenceUnavailable("model_stream_invalid")
                        if frame.get("model") != MODEL:
                            raise InferenceUnavailable("model_version_mismatch")
                        if "error" in frame:
                            raise InferenceUnavailable("model_unavailable")
                        if type(frame.get("done")) is not bool or not isinstance(frame.get("response"), str):
                            raise InferenceUnavailable("model_stream_invalid")
                        delta = frame["response"]
                        text += delta
                        if delta:
                            first = first if first is not None else time.monotonic() - began
                            yield InferenceDelta(delta)
                        if frame["done"]:
                            terminal = frame
                if terminal is None or not text or terminal.get("done_reason") not in {"stop", "length"}:
                    raise InferenceUnavailable("model_output_incomplete")
                counts = (terminal.get("prompt_eval_count"), terminal.get("eval_count"))
                if type(counts[0]) is not int or type(counts[1]) is not int:
                    raise InferenceUnavailable("model_usage_invalid")
                if counts[0] < 0 or counts[1] < 0:
                    raise InferenceUnavailable("model_usage_invalid")
                if counts[1] > request.max_output_tokens or counts[0] > request.context_tokens:
                    raise InferenceUnavailable("model_token_limit_exceeded")
                yield InferenceResult(
                    MODEL,
                    text,
                    Usage(*counts, cash_actual_microusd=0),
                    time.monotonic() - began,
                    first,
                    finish_reason=terminal["done_reason"],
                )
        except (TimeoutError, httpx.HTTPError):
            raise InferenceUnavailable("model_timeout_or_response_unknown") from None
        except (ValueError, TypeError, KeyError):
            raise InferenceUnavailable("model_stream_invalid") from None
        finally:
            self.capacity.release()

    async def unload(self) -> None:
        if not self.capacity.acquire(blocking=False):
            raise InferenceUnavailable("model_busy")
        try:
            async with self._client(10) as client, asyncio.timeout(10):
                result = await client.post("/api/generate", json={"model": MODEL, "keep_alive": 0, "stream": False})
                if result.status_code != 200:
                    raise InferenceUnavailable("model_unload_failed")
        except (TimeoutError, httpx.HTTPError):
            raise InferenceUnavailable("model_unload_unknown") from None
        finally:
            self.capacity.release()

    async def status(self) -> dict[str, Any]:
        try:
            async with self._client(5) as client, asyncio.timeout(5):
                await self._pinned(client)
                response = await client.get("/api/ps")
                if response.status_code != 200 or len(response.content) > 65536:
                    raise InferenceUnavailable("model_status_unavailable")
                body: dict[str, Any] = response.json()
                return body
        except (TimeoutError, httpx.HTTPError):
            raise InferenceUnavailable("model_status_unavailable") from None

    async def embed(self, text: str) -> None:
        raise InferenceUnavailable("embedding_model_not_configured")
