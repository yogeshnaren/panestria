"""Request identity/compatibility behavior with explicitly synthetic public metadata."""

import asyncio
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import httpx2 as httpx
import pytest
from pydantic import ValidationError

from model_manifest_support import model_manifest
from panestria.contracts.inference import InferenceRequest, InferenceUnavailable
from panestria.contracts.model_manifest import ModelManifest
from panestria.inference.local import LocalProvider
from panestria.inference.runtime import MODEL, MODEL_DIGEST


def test_compatibility_refuses_unknown_tokenizer_template_tools_and_preserves_legacy_hash():
    selected = model_manifest()
    for change in (
        {"tokenizer_container_sha256": "8" * 64},
        {"template_sha256": "8" * 64},
        {"tools": ("shell",)},
        {"quantization": "UNKNOWN"},
        {"max_context_tokens": 2048},
    ):
        assert not selected.context_compatible(model_manifest(**change))
    assert selected.context_compatible(model_manifest(engine_sha256="8" * 64))
    assert selected.sha256() != model_manifest(engine_sha256="8" * 64).sha256()
    for version in (True, "1", 2):
        with pytest.raises(ValidationError):
            ModelManifest.model_validate({**selected.model_dump(), "schema_version": version})
    body = dict(
        owner_id=str(uuid4()),
        project_id=str(uuid4()),
        request_id=str(uuid4()),
        model_ref=MODEL,
        prompt="PUBLIC synthetic",
        label="PUBLIC",
        trace_id=uuid4().hex,
    )
    old = InferenceRequest.model_validate(body)
    assert "model_manifest_sha256" not in old.model_dump() and "model_manifest_sha256" not in old.model_dump_json()
    assert (
        old.sha256()
        == hashlib.sha256(json.dumps(old.model_dump(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    )


def test_bound_provider_requires_exact_identity_and_cannot_rebind_in_place():
    selected = model_manifest()
    calls = []

    async def handle(request):
        calls.append(request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": MODEL, "digest": MODEL_DIGEST}]})
        return httpx.Response(
            200,
            content=json.dumps(
                {
                    "model": MODEL,
                    "response": "READY",
                    "done": True,
                    "done_reason": "stop",
                    "prompt_eval_count": 10,
                    "eval_count": 1,
                }
            ),
        )

    provider = LocalProvider(Path("/synthetic"), transport=httpx.MockTransport(handle))
    provider.bind_manifest(selected)
    request = InferenceRequest(
        owner_id=str(uuid4()),
        project_id=str(uuid4()),
        request_id=str(uuid4()),
        model_ref=MODEL,
        prompt="PUBLIC synthetic",
        label="PUBLIC",
        trace_id=uuid4().hex,
        model_manifest_sha256=selected.sha256(),
    )
    for digest in (None, "9" * 64):
        with pytest.raises(InferenceUnavailable, match="model_manifest_mismatch"):
            provider.generate(request.model_copy(update={"model_manifest_sha256": digest}))
        assert not calls
    result = provider.generate(request)
    assert result.text == "READY" and result.model_manifest_sha256 == selected.sha256()
    assert len(calls) == 2
    with pytest.raises(InferenceUnavailable, match="model_manifest_not_supported"):
        provider.bind_manifest(model_manifest(engine_sha256="9" * 64))
    assert provider.model_manifest == selected
    # Losing the pin is not a legacy fallback, even with the same friendly name.
    legacy = LocalProvider(Path("/synthetic"), transport=httpx.MockTransport(handle))
    with pytest.raises(InferenceUnavailable, match="model_manifest_mismatch"):
        legacy.generate(request)
    assert len(calls) == 2


def test_provider_configuration_change_after_return_refuses_completed_result():
    provider = None

    async def handle(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": MODEL, "digest": MODEL_DIGEST}]})
        provider.json_output = True  # Explicit controller configuration-change fault.
        return httpx.Response(
            200,
            content=json.dumps(
                {
                    "model": MODEL,
                    "response": "MUST_NOT_PUBLISH",
                    "done": True,
                    "done_reason": "stop",
                    "prompt_eval_count": 10,
                    "eval_count": 1,
                }
            ),
        )

    provider = LocalProvider(Path("/synthetic"), transport=httpx.MockTransport(handle))
    selected = model_manifest()
    provider.bind_manifest(selected)
    request = InferenceRequest(
        owner_id=str(uuid4()),
        project_id=str(uuid4()),
        request_id=str(uuid4()),
        model_ref=MODEL,
        prompt="PUBLIC synthetic",
        label="PUBLIC",
        trace_id=uuid4().hex,
        model_manifest_sha256=selected.sha256(),
    )
    with pytest.raises(InferenceUnavailable, match="model_manifest_mismatch"):
        asyncio.run(provider.agenerate(request))
    assert provider.capacity.acquire(blocking=False)
    provider.capacity.release()
