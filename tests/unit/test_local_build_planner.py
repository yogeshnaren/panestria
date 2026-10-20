"""Private proposal-only CLI flow; native/local generation is an explicit fixture."""

import hashlib
import json
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from typer.testing import CliRunner

from panestria.cli.main import app
from panestria.config_plan import PlanModelSettings
from panestria.contracts.goal import contract_sha256, load_contract
from panestria.contracts.inference import InferenceResult, Usage
from panestria.contracts.plan import PlanProposal, ProjectInventory
from panestria.execution.local_plan import LocalBuildPlanner, LocalPlanModel
from panestria.inference.runtime import MODEL
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.plans import PlanValidator

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def source_metadata(record_property, request):
    record_property(
        "candidate_commit", subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    )
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
    record_property("worktree_state", "dirty" if dirty else "clean")
    record_property("fixture_digest", hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    if not request.node.get_closest_marker("live"):
        record_property(
            "scope", "TEST_FIXTURE_NOT_LIVE generation; actual private CLI/typed graph/filesystem validation"
        )


@pytest.fixture
def planner_context(tmp_path):
    body = json.loads((ROOT / "docs/fixtures/synthetic-goal-contract.json").read_text())
    goal = load_contract(body)
    inventory = ProjectInventory.model_validate_json(
        json.dumps(
            {
                "owner_id": goal.owner_id,
                "project_id": goal.project_id,
                "base_commit": "ab" * 20,
                "snapshot_sha256": "cd" * 32,
                "workers": [
                    {
                        "worker_ref": role,
                        "capabilities": [capability],
                        "binary_sha256": "de" * 32,
                        "profile_sha256": "ef" * 32,
                        "maximum_parallel": 1,
                    }
                    for role, capability in (
                        ("worker-one", "scoped-file-edit"),
                        ("trusted-integrator", "trusted-test-runner"),
                    )
                ],
            }
        )
    )
    cache = tmp_path / "cache"
    cache.mkdir(mode=0o700)
    for name in ("blobs", "manifests"):
        (cache / name).mkdir()
    settings = PlanModelSettings(
        schema_version=1,
        owner_id=UUID(goal.owner_id),
        project_id=UUID(goal.project_id),
        model_cache=cache,
        runtime_directory=tmp_path / "model-runtime",
    )
    draft = {
        "edits": [
            {
                "task_id": "edit-one",
                "worker_ref": "worker-one",
                "capabilities": ["scoped-file-edit"],
                "paths": ["src/example.py"],
                "acceptance_keys": ["AC-002"],
                "wall_seconds_per_attempt": 60,
            },
        ]
    }
    state = SimpleNamespace(calls=[], draft=draft, finish_reason="stop")

    class FixtureModel:
        def generate(self, request):
            state.calls.append(request)
            return InferenceResult(
                MODEL, json.dumps(state.draft), Usage(100, 100), 0.25, None, finish_reason=state.finish_reason
            )

    return SimpleNamespace(
        goal=goal,
        inventory=inventory,
        settings=settings,
        model=FixtureModel(),
        state=state,
        output=tmp_path / "proposal",
        root=tmp_path,
    )


def test_one_private_draft_is_validated_bound_to_inputs_and_never_implicitly_replayed(planner_context):
    f = planner_context
    planner = LocalBuildPlanner(f.settings, f.model)
    receipt = planner.propose(f.goal, f.inventory, f.output, local_model_run=True)
    assert len(f.state.calls) == 1 and f.state.calls[0].offline and f.state.calls[0].label == "RESTRICTED"
    assert receipt["status"] == "VALIDATED_DRAFT" and receipt["execution_authority"] == "NONE"
    assert receipt["canonical_plan_state"] == "NOT_STAGED"
    proposal = PlanProposal.model_validate_json((f.output / "proposal.json").read_bytes())
    validation = PlanValidator().validate(Actor(f.goal.owner_id, f.goal.project_id), proposal, f.goal, f.inventory)
    assert validation.proposal_sha256 == receipt["proposal_sha256"]
    assert proposal.contract_sha256 == contract_sha256(f.goal) and proposal.inventory_sha256 == f.inventory.sha256()
    assert all(str(UUID(n.task_id)) == n.task_id for n in proposal.nodes)
    assert len(validation.layers) == 2 and validation.upper_wall_seconds == 120
    before = (f.output / "result.json").read_bytes()
    with pytest.raises(KernelDenied, match="fresh_private_plan_output_required"):
        planner.propose(f.goal, f.inventory, f.output, local_model_run=True)
    assert len(f.state.calls) == 1 and (f.output / "result.json").read_bytes() == before
    assert stat.S_IMODE(f.output.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in f.output.iterdir())


@pytest.mark.parametrize("fault", ["outside-path", "cycle", "authority-field", "truncated"])
def test_bad_model_output_retains_failure_but_cannot_publish_or_retry(planner_context, fault):
    f = planner_context
    if fault == "outside-path":
        f.state.draft["edits"][0]["paths"] = ["secrets/escape.txt"]
    elif fault == "cycle":
        f.state.draft["edits"][0]["depends_on"] = ["edit-one"]
    elif fault == "authority-field":
        f.state.draft["edits"][0]["shell_command"] = "arbitrary command is not authority"
    else:
        f.state.finish_reason = "length"
    planner = LocalBuildPlanner(f.settings, f.model)
    with pytest.raises((KernelDenied, ValueError)):
        planner.propose(f.goal, f.inventory, f.output, local_model_run=True)
    receipt = json.loads((f.output / "result.json").read_bytes())
    assert receipt["status"] == "UNAVAILABLE" and not (f.output / "proposal.json").exists()
    assert receipt["automatic_retry"] is False and len(f.state.calls) == 1
    assert (f.output / "request.json").exists()
    if fault != "truncated":
        assert (f.output / "response.txt").exists()
    with pytest.raises(KernelDenied):
        planner.propose(f.goal, f.inventory, f.output, local_model_run=True)
    assert len(f.state.calls) == 1


def test_missing_intent_foreign_scope_and_oversized_inputs_refuse_before_model(planner_context):
    f = planner_context
    planner = LocalBuildPlanner(f.settings, f.model)
    with pytest.raises(KernelDenied, match="explicit_local_plan_model_intent_required"):
        planner.propose(f.goal, f.inventory, f.output, local_model_run=False)
    foreign = f.settings.model_copy(update={"project_id": uuid4()})
    with pytest.raises(KernelDenied, match="local_plan_scope_or_cash_invalid"):
        LocalBuildPlanner(foreign, f.model).propose(f.goal, f.inventory, f.output, local_model_run=True)
    body = f.goal.model_dump(mode="json")
    body["intent"] = "long requirement " * 100
    with pytest.raises(KernelDenied, match="local_plan_context_limit"):
        planner.propose(load_contract(body), f.inventory, f.output, local_model_run=True)
    assert not f.state.calls and not f.output.exists()


def test_actual_private_cli_generates_review_files_without_database_or_native_authority(planner_context, monkeypatch):
    f = planner_context
    config, contract, inventory = (f.root / (name + ".json") for name in ("model", "contract", "inventory"))
    for path, value in ((config, f.settings), (contract, f.goal), (inventory, f.inventory)):
        path.write_text(value.model_dump_json())
        path.chmod(0o600)
    monkeypatch.setattr(LocalPlanModel, "generate", lambda _self, request: f.model.generate(request))
    result = CliRunner().invoke(
        app,
        [
            "plan",
            "propose",
            "--config",
            str(config),
            "--contract",
            str(contract),
            "--inventory",
            str(inventory),
            "--output-directory",
            str(f.output),
            "--local-model-run",
        ],
    )
    assert result.exit_code == 0, (result.stdout, result.exception)
    assert json.loads(result.stdout)["status"] == "VALIDATED_DRAFT"
    assert f.goal.intent not in result.stdout and len(f.state.calls) == 1
    proposal = PlanProposal.model_validate_json((f.output / "proposal.json").read_bytes())
    assert proposal.goal_id == f.goal.goal_id


@pytest.mark.live
def test_actual_cpu_produces_an_offline_validated_plan(planner_context, record_property):
    import os

    from panestria.inference.runtime import MODEL_DIGEST

    cache = os.environ.get("PANESTRIA_PROFILE_TEST_MODEL_CACHE")
    if not cache:
        pytest.skip("Explicit existing model cache required; no download")
    controllers = subprocess.check_output(
        ["docker", "ps", "-a", "-q", "--filter", "label=panestria.purpose=local-model"], text=True
    ).split()
    assert not controllers, "Owner model controller preserved; live draft not run"
    f = planner_context
    body = f.goal.model_dump(mode="json")
    body["intent"] = "Create src/example.py with a double(value) function returning value * 2. Change no other file."
    body["budget"]["max_wall_seconds"] = 270
    settings = f.settings.model_copy(update={"model_cache": Path(cache)})
    receipt = LocalBuildPlanner(settings).propose(load_contract(body), f.inventory, f.output, local_model_run=True)
    assert receipt["status"] == "VALIDATED_DRAFT"
    proposal = PlanProposal.model_validate_json((f.output / "proposal.json").read_bytes())
    assert proposal.nodes and receipt["execution_authority"] == "NONE"
    assert receipt["usage"]["input_tokens"] > 0 and receipt["usage"]["output_tokens"] > 0
    assert not subprocess.check_output(
        ["docker", "ps", "-a", "-q", "--filter", "label=panestria.purpose=local-model"], text=True
    ).split()
    record_property(
        "scope",
        "Actual network-disabled local CPU model, typed validated proposal only; no DB, worker or release authority",
    )
    record_property("model_ref", MODEL)
    record_property("model_digest", MODEL_DIGEST)
    record_property("response_sha256", receipt["response_sha256"])
    record_property("proposal_sha256", receipt["proposal_sha256"])
    record_property("elapsed_seconds", receipt["elapsed_seconds"])
    record_property("usage", json.dumps(receipt["usage"]))
    record_property("release_gate", "NOT_EVALUATED")
