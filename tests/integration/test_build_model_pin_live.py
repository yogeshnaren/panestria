"""Actual cached model: observed Ask identity becomes a preselected JSON draft pin."""

import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from panestria.api.local_server import build_local_app
from panestria.cli.local_init import first_run_files
from panestria.config import Settings
from panestria.config_local import load_local_settings
from panestria.config_plan import PlanModelSettings, expected_plan_manifest
from panestria.contracts.inference import InferenceRequest
from panestria.contracts.model_manifest import ModelManifest
from panestria.execution.local_plan import LocalPlanModel
from panestria.inference.runtime import MODEL
from panestria.kernel.local_setup import LocalSetupIntent, LocalSetupService
from panestria.kernel.uow import UnitOfWork


@pytest.mark.live
def test_actual_cached_cpu_json_uses_preselected_manifest(r1_database, tmp_path_factory, record_property):
    cache = os.environ.get("PANESTRIA_PROFILE_TEST_MODEL_CACHE")
    if not cache:
        pytest.skip("explicit existing read-only cache required; no download or live evidence")
    root = tmp_path_factory.mktemp("jsonpin") / "owner-test"
    with first_run_files(root, Path(cache), 18763) as config:
        with psycopg.connect(r1_database) as c:
            LocalSetupService().initialize(
                UnitOfWork(c),
                LocalSetupIntent(
                    owner_id=config.owner_id,
                    project_id=config.project_id,
                    intent="OFFLINE_ASK",
                ),
            )
    path = root / "local.json"
    path.write_text(json.dumps({**json.loads(path.read_text()), "pin_model_manifest": True}))
    config, token = load_local_settings(path)
    app = build_local_app(config, Settings(database_url=r1_database).validate_profile(), token.get_secret_value())
    model = app.state.local_model
    assert not model._docker(["ps", "-a", "-q", "--filter", "label=panestria.purpose=local-model"]).strip()
    # Observe public identity without generating. This is expectation data, not
    # a new quality/runtime certificate. Stop only this owned Ask runtime first.
    with TestClient(app, base_url=config.origin) as client:
        body = client.get("/v1/local/status", headers={"Authorization": "Bearer " + token.get_secret_value()}).json()
        selected = ModelManifest.model_validate_json(json.dumps(body["model_manifest"])).for_json_output()
    assert model.id is None
    expected = root / "expected-json.json"
    expected.write_text(selected.model_dump_json())
    expected.chmod(0o600)
    settings = PlanModelSettings(
        schema_version=1,
        owner_id=config.owner_id,
        project_id=config.project_id,
        model_cache=Path(cache),
        runtime_directory=root / "draft-runtime",
        model_manifest_file=expected,
    )
    assert expected_plan_manifest(settings) == selected
    request = InferenceRequest(
        owner_id=str(config.owner_id),
        project_id=str(config.project_id),
        request_id=str(uuid4()),
        model_ref=MODEL,
        prompt='Return ONLY the JSON object {"ready":true}.',
        label="PUBLIC",
        trace_id=uuid4().hex,
        max_output_tokens=32,
        deadline_seconds=60.0,
        model_manifest_sha256=selected.sha256(),
    )
    result = LocalPlanModel(settings).generate(request)
    assert isinstance(json.loads(result.text), dict) and result.model_manifest_sha256 == selected.sha256()
    assert result.usage.input_tokens > 0 and result.usage.output_tokens > 0
    assert not model._docker(["ps", "-a", "-q", "--filter", "label=panestria.purpose=local-model"]).strip()
    record_property("candidate_commit", subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip())
    record_property("execution_mode", "ACTUAL_CACHED_CPU_STARTUP_UDS_JSON_PG_ASGI_METADATA__NO_TCP_OR_PLAN_QUALITY")
    record_property("model_calls", 1)
    record_property("model_manifest_sha256", selected.sha256())
    record_property("model_elapsed_seconds", result.elapsed_seconds)
    record_property("model_input_tokens", result.usage.input_tokens)
    record_property("model_output_tokens", result.usage.output_tokens)
    record_property("release_gate", "NOT_EVALUATED")
