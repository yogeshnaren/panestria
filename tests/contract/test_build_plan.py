"""AOS-025-S1 pure proposal checks; no worker, certified inventory or release authority."""

import copy
import hashlib
import json
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from panestria.cli.main import app
from panestria.contracts.goal import contract_sha256, load_contract
from panestria.contracts.plan import PlanProposal, ProjectInventory
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.plans import PlanValidator

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def source_metadata(record_property):
    record_property(
        "candidate_commit", subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    )
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
    record_property("worktree_state", "dirty" if dirty else "clean")
    record_property("scope", "AOS-025-S1 partial TC01 proposal validation; no dispatch, canonical plan or release pass")
    record_property("fixture_digest", hashlib.sha256(Path(__file__).read_bytes()).hexdigest())


@pytest.fixture
def context():
    body = json.loads((ROOT / "docs/fixtures/synthetic-goal-contract.json").read_bytes())
    contract = load_contract(body)
    inventory = ProjectInventory.model_validate_json(
        json.dumps(
            {
                "owner_id": contract.owner_id,
                "project_id": contract.project_id,
                "base_commit": "ab" * 20,
                "snapshot_sha256": "ef" * 32,
                "workers": [
                    {
                        "worker_ref": worker,
                        "binary_sha256": "ab" * 32,
                        "profile_sha256": "cd" * 32,
                        "capabilities": ["scoped-file-edit"],
                        "maximum_parallel": 1,
                    }
                    for worker in ("worker-one", "worker-two")
                ],
            }
        )
    )
    keys = [c.id for c in contract.acceptance]
    ids = [str(uuid4()) for _ in range(3)]
    nodes = [
        {
            "task_id": ids[i],
            "depends_on": [] if i < 2 else ids[:2],
            "worker_ref": "worker-two" if i == 1 else "worker-one",
            "capabilities": ["scoped-file-edit"],
            "paths": [f"src/part{i}.py"],
            "acceptance_keys": [keys[i]],
            "expected_artifacts": [f"patch-{i}"],
            "attempts": 1,
            "wall_seconds_per_attempt": 20,
            "api_microusd_per_attempt": 0,
        }
        for i in range(3)
    ]
    proposal = {
        "plan_id": str(uuid4()),
        "owner_id": contract.owner_id,
        "project_id": contract.project_id,
        "goal_id": contract.goal_id,
        "contract_sha256": contract_sha256(contract),
        "inventory_sha256": inventory.sha256(),
        "privacy_class": contract.privacy_class,
        "nodes": nodes,
    }
    return body, contract, inventory, proposal


def validate(context, proposal=None, inventory=None):
    _, contract, available, document = context
    return PlanValidator().validate(
        Actor(contract.owner_id, contract.project_id),
        PlanProposal.model_validate_json(json.dumps(document if proposal is None else proposal)),
        contract,
        available if inventory is None else inventory,
    )


def test_independent_nodes_then_join_have_bounded_deterministic_proposal_only_layers(context):
    _, contract, _, proposal = context
    result = validate(context)
    ids = [n["task_id"] for n in proposal["nodes"]]
    assert result.layers == (tuple(sorted(ids[:2])), (ids[2],))
    assert result.upper_wall_seconds == 60 and result.upper_api_microusd == 0
    assert result.maximum_parallel == 2 and result.authority == "PROPOSAL_ONLY"
    assert result.contract_sha256 == contract_sha256(contract)
    assert result == validate(context, proposal=json.loads(json.dumps(proposal, sort_keys=True)))
    one = copy.deepcopy(proposal)
    one["nodes"] = [one["nodes"][0]]
    one["nodes"][0]["acceptance_keys"] = [c.id for c in contract.acceptance]
    assert len(validate(context, proposal=one).layers) == 1


@pytest.mark.parametrize(
    "fault,code",
    [
        ("cycle", "plan_cycle"),
        ("self", "plan_dependency_invalid"),
        ("missing-parent", "plan_dependency_invalid"),
        ("duplicate", "plan_duplicate_task"),
        ("worker", "plan_capability_unavailable"),
        ("worker-capability", "plan_capability_unavailable"),
        ("contract-capability", "plan_capability_unavailable"),
        ("path", "plan_path_out_of_scope"),
        ("missing-check", "plan_required_checks_missing"),
        ("unknown-check", "plan_check_unrecognized"),
        ("attempts", "plan_attempt_limit"),
        ("wall", "plan_budget_exceeded"),
        ("cash", "plan_budget_exceeded"),
        ("owner", "plan_scope_mismatch"),
        ("goal", "plan_scope_mismatch"),
        ("contract", "plan_input_binding_changed"),
        ("inventory", "plan_input_binding_changed"),
        ("privacy", "plan_input_binding_changed"),
        ("nodes", "plan_node_limit"),
        ("depth", "plan_depth_limit"),
    ],
)
def test_invalid_proposals_cannot_enter_a_validated_dag(context, fault, code):
    document, contract, inventory, proposal = context
    body = copy.deepcopy(proposal)
    node = body["nodes"][0]
    if fault == "cycle":
        node["depends_on"] = [body["nodes"][2]["task_id"]]
    elif fault == "self":
        node["depends_on"] = [node["task_id"]]
    elif fault == "missing-parent":
        node["depends_on"] = [str(uuid4())]
    elif fault == "duplicate":
        body["nodes"].append(copy.deepcopy(node))
    elif fault == "worker":
        node["worker_ref"] = "unavailable"
    elif fault == "worker-capability":
        node["capabilities"] = ["trusted-test-runner"]
    elif fault == "contract-capability":
        inv = inventory.model_dump(mode="json")
        inv["workers"][0]["capabilities"].append("external-send")
        inventory = ProjectInventory.model_validate_json(json.dumps(inv))
        body["inventory_sha256"] = inventory.sha256()
        node["capabilities"] = ["external-send"]
    elif fault == "path":
        node["paths"] = ["secrets/access.txt"]
    elif fault == "missing-check":
        node["acceptance_keys"] = body["nodes"][1]["acceptance_keys"]
    elif fault == "unknown-check":
        node["acceptance_keys"] = ["owner-never-requested-this"]
    elif fault == "attempts":
        node["attempts"] = 3
    elif fault == "wall":
        node["wall_seconds_per_attempt"] = 121
    elif fault == "cash":
        node["api_microusd_per_attempt"] = 1
    elif fault in {"owner", "goal"}:
        body[fault + "_id"] = str(uuid4())
    elif fault in {"contract", "inventory"}:
        body[fault + "_sha256"] = "bb" * 32
    elif fault == "privacy":
        body["privacy_class"] = "PUBLIC"
    else:
        inv = inventory.model_dump(mode="json")
        inv["maximum_" + fault] = 1
        inventory = ProjectInventory.model_validate_json(json.dumps(inv))
        body["inventory_sha256"] = inventory.sha256()
    with pytest.raises(KernelDenied, match=code):
        validate((document, contract, inventory, proposal), proposal=body)


@pytest.mark.parametrize(
    "path",
    [
        "../escape",
        "/absolute",
        "src//empty",
        "src/../outside",
        ".git/config",
        "src/\ncontrol",
        "src/a;run",
        "src/*",
        "src/./alias",
        "src/café.py",
    ],
)
def test_literal_paths_and_untrusted_authority_fields_are_closed(context, path):
    body = copy.deepcopy(context[3])
    body["nodes"][0]["paths"] = [path]
    with pytest.raises(ValidationError):
        validate(context, proposal=body)


def test_private_cli_preflight_and_forged_model_copy_cannot_dispatch_or_expose_inputs(context, tmp_path):
    body, contract, inventory, proposal = context
    for name, value in (("contract", body), ("inventory", inventory.model_dump(mode="json")), ("proposal", proposal)):
        p = tmp_path / (name + ".json")
        p.write_text(json.dumps(value))
        p.chmod(0o600)
    args = ["plan", "validate", contract.owner_id, contract.project_id]
    for name in ("proposal", "contract", "inventory"):
        args += ["--" + name, str(tmp_path / (name + ".json"))]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["authority"] == "PROPOSAL_ONLY"
    assert "part0.py" not in result.output and str(tmp_path) not in result.output
    corrupted = PlanProposal.model_validate_json(json.dumps(proposal)).model_copy(update={"nodes": ()})
    with pytest.raises(ValidationError):
        PlanValidator().validate(Actor(contract.owner_id, contract.project_id), corrupted, contract, inventory)
    proposal["approved"] = True
    (tmp_path / "proposal.json").write_text(json.dumps(proposal))
    rejected = CliRunner().invoke(app, args)
    assert rejected.exit_code == 1 and "plan_proposal_rejected" in rejected.output
    assert str(tmp_path) not in rejected.output and contract.intent not in rejected.output
