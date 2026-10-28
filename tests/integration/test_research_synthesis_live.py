"""One actual local CPU draft from retained synthetic transport data; not G2 qualification."""

import hashlib
import os
import subprocess
from pathlib import Path

import pytest
from test_research_synthesis import observations, research, synthesis_context  # noqa: F401 -- fixture chain

from panestria.execution.research_synthesis import OwnerSynthesis


@pytest.mark.live
def test_actual_cpu_draft_uses_retained_sources_and_no_provider(synthesis_context, record_property):  # noqa: F811
    cache = os.environ.get("PANESTRIA_PROFILE_TEST_MODEL_CACHE")
    if not cache:
        pytest.skip("Explicit existing local cache required; no downloads")
    controllers = subprocess.check_output(
        ["docker", "ps", "-a", "-q", "--no-trunc", "--filter", "label=panestria.purpose=local-model"], text=True
    ).split()
    assert not controllers, "Owner model controller preserved; live check not run"
    service, request = synthesis_context
    service = OwnerSynthesis(service.dsn, service.settings.model_copy(update={"model_cache": Path(cache)}))
    receipt = service.synthesize(request.request_id, "actual-local-synthetic", retain_local_draft=True)
    assert receipt.status == "DRAFT_RETAINED"
    draft = service.inspect(request.request_id)
    assert draft.response.claims and draft.packet.passages
    assert all(set(claim.citations) <= {p.citation for p in draft.packet.passages} for claim in draft.response.claims)
    assert draft.semantic_support == "NOT_ASSESSED" and draft.task_completion_authority == "NONE"
    assert draft.input_tokens > 0 and draft.output_tokens > 0
    assert not subprocess.check_output(
        ["docker", "ps", "-a", "-q", "--no-trunc", "--filter", "label=panestria.purpose=local-model"], text=True
    ).split()
    record_property("execution_mode", "ACTUAL_POSTGRES_CAS_READER_NETWORK_NONE_LOCAL_CPU_MODEL")
    record_property("fetch_transport", "SYNTHETIC_NOT_PUBLIC_TLS_OR_SEARCH")
    record_property("model_mocked", False)
    record_property("input_sha256", draft.input_sha256)
    record_property("output_sha256", receipt.output_sha256)
    record_property("model_ref", draft.model_ref)
    record_property("model_digest", draft.model_digest)
    record_property(
        "runtime_bridge_sha256",
        hashlib.sha256(
            (Path(__file__).resolve().parents[2] / "src/panestria/inference/runtime_bridge.py").read_bytes()
        ).hexdigest(),
    )
    record_property("input_tokens", draft.input_tokens)
    record_property("output_tokens", draft.output_tokens)
    record_property("release_gate", "NOT_EVALUATED")
