"""Injected provider outcomes qualify protocol/stop guards only, not local inference."""

import asyncio
import json
import threading
from pathlib import Path

import pytest

from panestria.contracts.inference import InferenceResult, InferenceUnavailable, Usage
from panestria.execution.entailment_probe import LocalEntailmentProbe
from panestria.inference.local import LocalProvider
from panestria.inference.runtime import MODEL

CORPUS = Path(__file__).resolve().parents[1] / "fixtures/research/snli-v1/corpus.json"


@pytest.mark.parametrize(
    "response,reason",
    [
        ('{"verdict":"UNKNOWN"}', "closed_verdict"),
        ('```json\n{"verdict":"SUPPORTED"}\n```', "closed_verdict"),
        ('{"verdict":"SUPPORTED","approved":true}', "invalid_verdict"),
        ('{"verdict":"SUPPORTED","verdict":"UNKNOWN"}', "invalid_verdict"),
        ("not JSON", "invalid_verdict"),
        ("\ud800", "invalid_verdict"),
    ],
)
def test_injected_outputs_keep_unknown_and_refuse_extra_or_duplicate_fields(monkeypatch, response, reason):
    calls = []

    async def injected(_self, request):
        calls.append(request)
        assert request.offline and request.label == "PUBLIC" and request.model_ref == MODEL
        payload = json.loads(request.prompt.split("\n", 1)[1])
        assert set(payload) == {"premise", "hypothesis"}  # No gold/source metadata.
        return InferenceResult(MODEL, response, Usage(150, 12, cash_actual_microusd=0), 0.1, 0.01)

    monkeypatch.setattr(LocalProvider, "agenerate", injected)
    result = asyncio.run(LocalEntailmentProbe(LocalProvider(Path("/synthetic-no-socket"))).run(CORPUS, "calibration"))
    assert result.status == "COMPLETE" and len(calls) == len(result.cases) == 36
    assert all(c.reason == reason for c in result.cases)
    if reason == "invalid_verdict":
        assert all(c.prediction.verdict == "UNKNOWN" for c in result.cases)
    assert result.authority == "LOCAL_MODEL_OBSERVATION_ONLY"


def test_provider_failure_retains_only_called_cases_and_has_no_fake_full_score(monkeypatch):
    calls = []

    async def injected(_self, request):
        calls.append(request)
        if len(calls) == 2:
            raise InferenceUnavailable("synthetic unavailable")
        return InferenceResult(MODEL, '{"verdict":"UNKNOWN"}', Usage(150, 12), 0.1, 0.01)

    monkeypatch.setattr(LocalProvider, "agenerate", injected)
    result = asyncio.run(LocalEntailmentProbe(LocalProvider(Path("/synthetic-no-socket"))).run(CORPUS, "qualification"))
    assert result.status == "INCOMPLETE" and result.reason == "local_provider_unavailable"
    assert len(calls) == 2 and len(result.cases) == 1 and result.score is None


def test_cancelled_or_changed_corpus_never_dispatches(monkeypatch, tmp_path):
    async def forbidden(*_a, **_k):
        raise AssertionError("must not dispatch")

    monkeypatch.setattr(LocalProvider, "agenerate", forbidden)
    probe = LocalEntailmentProbe(LocalProvider(Path("/synthetic-no-socket")))
    event = threading.Event()
    event.set()
    result = asyncio.run(probe.run(CORPUS, "qualification", cancel=event))
    assert result.status == "INCOMPLETE" and not result.cases and result.score is None
    changed = tmp_path / "private-input.json"
    changed.write_text("synthetic private input")
    with pytest.raises(ValueError, match="entailment_corpus_unconfirmed"):
        asyncio.run(probe.run(changed, "qualification"))


def test_no_custom_transport_gpu_or_provider_subclass_can_be_selected():
    class Fake(LocalProvider):
        pass

    for provider in (LocalProvider(Path("/synthetic"), gpu=True), Fake(Path("/synthetic"))):
        with pytest.raises(ValueError, match="actual_local_provider_required"):
            LocalEntailmentProbe(provider)


def test_length_stopped_output_is_unknown_not_successful_closed_prediction(monkeypatch):
    async def injected(*_a, **_k):
        return InferenceResult(MODEL, '{"verdict":"SUPPORTED"}', Usage(150, 32), 0.1, 0.01, finish_reason="length")

    monkeypatch.setattr(LocalProvider, "agenerate", injected)
    result = asyncio.run(LocalEntailmentProbe(LocalProvider(Path("/synthetic"))).run(CORPUS, "calibration"))
    assert all(c.reason == "output_incomplete" and c.prediction.verdict == "UNKNOWN" for c in result.cases)
    assert result.score.supported_precision is None
