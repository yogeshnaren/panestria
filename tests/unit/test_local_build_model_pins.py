"""Actual typed draft/files/CLI; provider/runtime status are explicit fixtures."""

import json
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import httpx2 as httpx
import pytest
from test_local_build_planner import planner_context as planner_context  # noqa: F401
from typer.testing import CliRunner

from model_manifest_support import model_manifest
from panestria.cli.main import app
from panestria.cli.tui_client import LocalAskClient
from panestria.config_local import create_local_token
from panestria.contracts.inference import InferenceRequest, InferenceUnavailable
from panestria.execution.local_plan import LocalBuildPlanner
from panestria.inference.local import LocalProvider
from panestria.inference.runtime import MODEL, MODEL_DIGEST
from panestria.kernel.errors import KernelDenied


def test_json_profile_requires_explicit_format_and_returns_exact_identity():
    raw = model_manifest()
    selected = raw.for_json_output()
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
                    "response": '{"ready":true}',
                    "done": True,
                    "done_reason": "stop",
                    "prompt_eval_count": 10,
                    "eval_count": 5,
                }
            ),
        )

    provider = LocalProvider(Path("/synthetic"), transport=httpx.MockTransport(handle), json_output=True)
    with pytest.raises(InferenceUnavailable, match="model_manifest_not_supported"):
        provider.bind_manifest(raw)
    provider.bind_manifest(selected)
    request = InferenceRequest(
        owner_id=str(uuid4()),
        project_id=str(uuid4()),
        request_id=str(uuid4()),
        model_ref=MODEL,
        prompt="Return JSON",
        label="PUBLIC",
        trace_id=uuid4().hex,
        model_manifest_sha256=selected.sha256(),
    )
    result = provider.generate(request)
    assert result.model_manifest_sha256 == selected.sha256() and result.text == '{"ready":true}'
    assert json.loads(calls[-1].content)["format"] == "json" and len(calls) == 2


@pytest.mark.parametrize("wrong_return", [False, True])
def test_plan_intent_pins_before_dispatch_and_wrong_identity_cannot_publish(planner_context, wrong_return):
    f = planner_context
    selected = model_manifest().for_json_output()
    path = f.root / "expected.json"
    path.write_text(selected.model_dump_json())
    path.chmod(0o600)
    settings = f.settings.model_copy(update={"model_manifest_file": path})
    acknowledged = []

    def before_dispatch(request):
        # Exact disk journal/request precede this durable repair-admission hook.
        stored = InferenceRequest.model_validate_json((f.output / "request.json").read_bytes())
        receipt = json.loads((f.output / "result.json").read_bytes())
        assert request.sha256() == stored.sha256() == receipt["request_sha256"]
        assert request.model_manifest_sha256 == selected.sha256()
        assert receipt["model_manifest"] == selected.model_dump(mode="json")
        acknowledged.append(request.sha256())
        # A new-work file change after request preparation cannot repin this turn.
        path.write_text(model_manifest(template_sha256="9" * 64).for_json_output().model_dump_json())

    class Model:
        def generate(self, request):
            assert acknowledged == [request.sha256()]
            result = f.model.generate(request)
            return replace(result, model_manifest_sha256=None if wrong_return else selected.sha256())

    planner = LocalBuildPlanner(settings, Model())
    if wrong_return:
        with pytest.raises(KernelDenied, match="model_manifest_mismatch"):
            planner.propose(f.goal, f.inventory, f.output, local_model_run=True, before_dispatch=before_dispatch)
        assert not (f.output / "proposal.json").exists()
        assert json.loads((f.output / "result.json").read_bytes())["status"] == "UNAVAILABLE"
    else:
        receipt = planner.propose(
            f.goal,
            f.inventory,
            f.output,
            local_model_run=True,
            before_dispatch=before_dispatch,
        )
        assert receipt["model_manifest"] == selected.model_dump(mode="json")
        assert receipt["status"] == "VALIDATED_DRAFT" and receipt["execution_authority"] == "NONE"
    assert len(f.state.calls) == 1 and f.state.calls[0].model_manifest_sha256 == selected.sha256()


def test_owner_cli_exports_only_public_identity_as_explicit_json_expectation(tmp_path, monkeypatch):
    cache = tmp_path / "models"
    cache.mkdir()
    (cache / "blobs").mkdir()
    (cache / "manifests").mkdir()
    token = tmp_path / "token"
    create_local_token(token)
    config = tmp_path / "local.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "owner_id": str(uuid4()),
                "project_id": str(uuid4()),
                "token_file": str(token),
                "model_cache": str(cache),
                "runtime_directory": str(tmp_path / "runtime"),
            }
        )
    )
    config.chmod(0o600)
    selected = model_manifest()
    monkeypatch.setattr(LocalAskClient, "status", lambda self: {"model_manifest": selected.model_dump(mode="json")})
    output = tmp_path / "expected.json"
    args = ["local", "model-manifest", "--config", str(config), "--output", str(output), "--json-output"]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["qualification"] == "NOT_EVALUATED"
    assert json.loads(output.read_bytes()) == selected.for_json_output().model_dump(mode="json")
    assert output.stat().st_mode & 0o777 == 0o600
    assert token.read_text().strip() not in result.output + output.read_text()
    before = output.read_bytes()
    assert CliRunner().invoke(app, args).exit_code == 2 and output.read_bytes() == before
    assert (
        CliRunner()
        .invoke(
            app,
            [
                "local",
                "model-manifest",
                "--config",
                str(config),
                "--output",
                str(cache / "must-not-write.json"),
            ],
        )
        .exit_code
        == 2
    )
    assert not (cache / "must-not-write.json").exists()
