"""Own receipt allowlist/unknown/identity rules, no model or database."""

import json
from uuid import uuid4

import pytest

from panestria.contracts.model_manifest import ModelManifest
from panestria.telemetry.ask_metrics import ask_observation, capture_ask_metrics
from panestria.telemetry.performance import latest_snapshot

SENTINEL = "PRIVATE_PROMPT_RESPONSE_PROFILE_SENTINEL"


def receipt():
    return {
        "request_id": str(uuid4()),
        "context_pack_id": str(uuid4()),
        "state": "COMPLETED",
        "offline": True,
        "response_retained": False,
        "model_ref": "qwen2.5:1.5b-instruct",
        "usage": {
            "elapsed_seconds": 1.5,
            "first_token_seconds": 0.2,
            "input_tokens": 20,
            "output_tokens": 4,
            "cash_actual_microusd": None,
            "decode_tokens_per_second": None,
            "debug": SENTINEL,
        },
        "profile_context": {"private_debug": SENTINEL},
        "response_sha256": None,
        "response_digest_mode": "OMITTED_RESTRICTED_PROFILE",
        "sources": [{"title": SENTINEL}],
        "trace_id": SENTINEL,
    }


def test_private_receipt_allowlist_preserves_unknown_and_saves_one_case_not_a_distribution(tmp_path):
    doc = receipt()
    owner, project = str(uuid4()), str(uuid4())
    result = capture_ask_metrics(tmp_path / "metrics", owner, project, doc["request_id"], doc)
    snapshot = latest_snapshot(tmp_path / "metrics")
    values = {m.metric: m for m in snapshot.observations}
    assert values["latency.ask_generation"].value == 1.5 and values["latency.ask_generation"].samples == 1
    assert values["cost.actual"].value is None and values["cost.actual"].reason == "UNMEASURED"
    assert values["quality.correct_fraction"].value is None and values["quality.correct_fraction"].samples == 0
    assert all(m.source_commit is None for m in snapshot.observations)
    for p in (tmp_path / "metrics").rglob("*"):
        if p.is_file():
            assert SENTINEL not in p.read_text()
            assert p.stat().st_mode & 0o077 == 0
    assert result["authority"] == "DERIVED_MEASUREMENTS_ONLY"
    source = json.loads((tmp_path / "metrics/sources" / result["source_sha256"]).read_bytes())
    assert source["scope"] == "runtime_profile_ask" and source["runtime_build_source"] == "NOT_IN_RECEIPT"


def test_incomplete_receipt_does_not_reuse_success_timings_or_manufacture_zero(tmp_path):
    doc = receipt()
    doc["state"] = "CANCELLED"
    capture_ask_metrics(tmp_path / "metrics", str(uuid4()), str(uuid4()), doc["request_id"], doc)
    snapshot = latest_snapshot(tmp_path / "metrics")
    assert all(m.value is None and m.samples == 0 for m in snapshot.observations)
    assert all(m.reason == "INCOMPLETE_RUN" for m in snapshot.observations if m.metric != "quality.correct_fraction")


@pytest.mark.parametrize(
    "change",
    [
        {"text": SENTINEL},
        {"response_sha256": "a" * 64},
        {"offline": False},
        {"usage": {"elapsed_seconds": float("nan")}},
        {"usage": {"input_tokens": True}},
        {"usage": {"elapsed_seconds": 1.0, "first_token_seconds": 2.0}},
    ],
)
def test_malformed_receipt_never_creates_history(tmp_path, change):
    doc = receipt() | change
    with pytest.raises(ValueError):
        capture_ask_metrics(tmp_path / "metrics", str(uuid4()), str(uuid4()), doc["request_id"], doc)
    assert not (tmp_path / "metrics").exists()


def test_model_identity_must_match_canonical_context_and_completed_usage():
    doc = receipt()
    manifest = ModelManifest(
        model_ref=doc["model_ref"],
        model_bundle_sha256="1" * 64,
        weights_sha256="2" * 64,
        tokenizer_container_sha256="2" * 64,
        template_sha256="3" * 64,
        system_sha256="4" * 64,
        runtime_image="ubuntu@sha256:" + "5" * 64,
        engine_sha256="6" * 64,
        libraries_sha256="7" * 64,
        bridge_sha256="8" * 64,
        quantization="SYNTHETIC",
        license_refs=("9" * 64,),
    )
    doc["model_manifest"] = manifest.model_dump(mode="json")
    doc["usage"]["model_manifest_sha256"] = manifest.sha256()
    source = ask_observation(str(uuid4()), str(uuid4()), doc["request_id"], doc)
    assert source["weights_sha256"] == manifest.weights_sha256
    doc["usage"]["model_manifest_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="model_manifest_mismatch"):
        ask_observation(str(uuid4()), str(uuid4()), doc["request_id"], doc)
