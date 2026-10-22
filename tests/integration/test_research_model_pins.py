"""Actual PG/CAS/reader/intent/replay; model and HTTPS are explicit fixtures."""

import json

import pytest
from test_research_query_plan import planner as planner  # noqa: F401
from test_research_requests import research as research  # noqa: F401
from test_research_source_provenance import observations as observations  # noqa: F401
from test_research_submission import staged as staged  # noqa: F401
from test_research_synthesis import RESPONSE
from test_research_synthesis import synthesis_context as synthesis_context  # noqa: F401

from model_manifest_support import model_manifest
from panestria.contracts.inference import InferenceResult, Usage
from panestria.contracts.research_plan import plan_bytes
from panestria.contracts.research_synthesis import synthesis_json
from panestria.execution.research_query_plan import OwnerQueryPlan
from panestria.execution.research_synthesis import LocalDraftModel, OwnerSynthesis
from panestria.inference.runtime import MODEL
from panestria.kernel.errors import KernelDenied


def selected_file(root):
    selected = model_manifest().for_json_output()
    path = root / "expected-model.json"
    path.write_text(selected.model_dump_json())
    path.chmod(0o600)
    return path, selected


@pytest.mark.parametrize("wrong_identity", [False, True])
def test_query_intent_return_and_replay_bind_original_manifest(planner, monkeypatch, wrong_identity, record_property):
    prior, staged_request, _config = planner
    path, selected = selected_file(prior.settings.root)
    settings = prior.settings.model_copy(update={"model_manifest_file": path})
    service = OwnerQueryPlan(prior.artifacts.dsn, settings)
    calls = []

    def generate(self, request):
        with service.connect() as c:
            event = c.execute(
                "SELECT payload FROM panestria.task_event WHERE kind='research.query_plan.started'"
                " AND payload->>'request_id'=%s", (staged_request.request_id,),
            ).fetchone()[0]
        assert event["inference_request_sha256"] == request.sha256()
        assert event["model_manifest"] == selected.model_dump(mode="json")
        assert request.model_manifest_sha256 == self.manifest.sha256() == selected.sha256()
        path.rename(path.with_name("preserved-selection.json"))
        self.before_dispatch()
        calls.append(request)
        return InferenceResult(
            MODEL, json.dumps({"queries": ["synthetic source provenance"]}), Usage(100, 20, 0), 0.2, 0.1,
            model_manifest_sha256=None if wrong_identity else selected.sha256(),
        )

    monkeypatch.setattr(LocalDraftModel, "generate", generate)
    if wrong_identity:
        with pytest.raises(KernelDenied, match="model_manifest_mismatch"):
            service.plan(staged_request.request_id, "pin", retain_local_plan=True)
    else:
        result = service.plan(staged_request.request_id, "pin", retain_local_plan=True)
        assert result["status"] == "QUERY_PLAN_RETAINED" and result["web_authority"] == "NONE"
        retained = OwnerQueryPlan(prior.artifacts.dsn, settings).inspect(staged_request.request_id)
        assert retained.model_manifest == selected and retained.query_quality == "NOT_ASSESSED"
        assert json.loads(plan_bytes(retained))["model_manifest"] == selected.model_dump(mode="json")
        assert "model_manifest" not in json.loads(plan_bytes(retained.model_copy(update={"model_manifest": None})))
    replay = OwnerQueryPlan(prior.artifacts.dsn, settings).plan(
        staged_request.request_id, "pin", retain_local_plan=True,
    )
    assert replay["replayed"] and len(calls) == 1 and not path.exists()
    assert replay["status"] == ("FAILED" if wrong_identity else "QUERY_PLAN_RETAINED")
    record_property("execution_mode", "ACTUAL_PG_CAS_INTENT_REPLAY__EXPLICIT_MODEL_RUNTIME_FIXTURES__NO_WEB")


@pytest.mark.parametrize("wrong_identity", [False, True])
def test_synthesis_intent_return_and_inspection_keep_original_manifest(
    synthesis_context, monkeypatch, wrong_identity, record_property,
):
    prior, staged_request = synthesis_context
    path, selected = selected_file(prior.settings.root)
    settings = prior.settings.model_copy(update={"model_manifest_file": path})
    service = OwnerSynthesis(prior.dsn, settings)
    calls = []

    def generate(self, request):
        with service.connect() as c:
            event = c.execute(
                "SELECT payload FROM panestria.task_event WHERE kind='research.synthesis.started'"
                " AND payload->>'request_id'=%s", (staged_request.request_id,),
            ).fetchone()[0]
        assert event["inference_request_sha256"] == request.sha256()
        assert event["model_manifest"] == selected.model_dump(mode="json")
        assert request.model_manifest_sha256 == self.manifest.sha256() == selected.sha256()
        path.rename(path.with_name("preserved-selection.json"))
        self.before_dispatch()
        calls.append(request)
        return InferenceResult(
            MODEL, json.dumps(RESPONSE), Usage(123, 42, 0), 0.2, 0.1,
            model_manifest_sha256=None if wrong_identity else selected.sha256(),
        )

    monkeypatch.setattr(LocalDraftModel, "generate", generate)
    if wrong_identity:
        with pytest.raises(KernelDenied, match="model_manifest_mismatch"):
            service.synthesize(staged_request.request_id, "pin", retain_local_draft=True)
    else:
        result = service.synthesize(staged_request.request_id, "pin", retain_local_draft=True)
        assert result.status == "DRAFT_RETAINED" and result.task_completion_authority == "NONE"
        retained = OwnerSynthesis(prior.dsn, settings).inspect(staged_request.request_id)
        assert retained.model_manifest == selected and retained.semantic_support == "NOT_ASSESSED"
        assert json.loads(synthesis_json(retained))["model_manifest"] == selected.model_dump(mode="json")
        assert "model_manifest" not in json.loads(synthesis_json(retained.model_copy(update={"model_manifest": None})))
    replay = OwnerSynthesis(prior.dsn, settings).synthesize(staged_request.request_id, "pin", retain_local_draft=True)
    assert replay.replayed and len(calls) == 1 and not path.exists()
    assert replay.status == ("FAILED" if wrong_identity else "DRAFT_RETAINED")
    record_property("execution_mode", "ACTUAL_PG_CAS_READER_INTENT_REPLAY__EXPLICIT_MODEL_HTTPS_FIXTURES")
