"""AOS-002-TC01. Canonical contract hash and rejected legacy acceptance forms."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from panestria.contracts import ContractRejected, contract_sha256, load_contract, revise
from panestria.contracts.schema_export import rendered_schemas

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "docs" / "fixtures" / "synthetic-goal-contract.json"


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=ROOT, text=True, capture_output=True, check=False)


@pytest.fixture(autouse=True)
def _case_metadata(record_property: pytest.RecordProperty) -> None:
    commit = _run(["git", "rev-parse", "HEAD"]).stdout.strip()
    dirty = bool(_run(["git", "status", "--porcelain"]).stdout.strip())
    record_property("gate_case_id", "AOS-002-TC01")
    record_property("candidate_commit", commit)
    record_property("fixture_digest", hashlib.sha256(FIXTURE.read_bytes()).hexdigest())
    record_property("lane", "contract")
    record_property("execution_mode", "HERMETIC")
    record_property("worktree_state", "dirty" if dirty else "clean")


def _body() -> dict[str, object]:
    loaded: dict[str, object] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return loaded


def test_exported_json_schemas_match_the_models() -> None:
    directory = ROOT / "docs" / "contracts"
    rendered = rendered_schemas()
    stored = {path.name: path.read_text(encoding="utf-8") for path in directory.glob("*.schema.json")}
    assert stored == rendered


def test_canonical_hash_is_stable_across_key_order_and_money_spelling() -> None:
    first = load_contract(_body())
    reordered = {key: _body()[key] for key in reversed(list(_body()))}
    second = load_contract(reordered)
    spelled = _body()
    budget = dict(spelled["budget"])  # type: ignore[arg-type]
    budget["max_api_usd"] = "0"
    spelled["budget"] = budget
    third = load_contract(spelled)
    digest = contract_sha256(first)
    assert digest == contract_sha256(second) == contract_sha256(third)
    assert digest == contract_sha256(load_contract(json.loads(first.model_dump_json())))
    assert first.budget.max_api_usd == "0"


def test_edited_contract_creates_a_new_version() -> None:
    current = load_contract(_body())
    edited = current.model_copy(update={"intent": current.intent + " again"})
    revised = revise(current, edited)
    assert revised.contract_version == current.contract_version + 1
    assert contract_sha256(revised) != contract_sha256(current)
    assert revise(current, current) is current
    moved = current.model_copy(update={"owner_id": "00000000-0000-4000-8000-000000000099"})
    with pytest.raises(ContractRejected) as moved_error:
        revise(current, moved)
    assert moved_error.value.code == "identity_changed"


def test_legacy_raw_command_bool_budget_and_duplicate_ids_are_rejected() -> None:
    legacy = _body()
    legacy["acceptance"] = [
        {
            "id": "AC-LEGACY",
            "description": "raw shell",
            "required": True,
            "verifier": {"type": "command", "run": "pytest -q tests/secret"},
            "evidence": {"required": True, "kind": "report"},
        }
    ]
    with pytest.raises(ContractRejected) as legacy_error:
        load_contract(legacy)
    assert legacy_error.value.code == "legacy_verifier"
    assert "pytest" not in str(legacy_error.value)

    shell = _body()
    checks = shell["acceptance"]
    assert isinstance(checks, list)
    first = dict(checks[0])
    verifier = dict(first["verifier"])
    verifier["command_ref"] = "pytest -q"
    first["verifier"] = verifier
    shell["acceptance"] = [first]
    with pytest.raises(ContractRejected) as shell_error:
        load_contract(shell)
    assert shell_error.value.code == "invalid_command_ref"
    assert "pytest" not in str(shell_error.value)

    boolean = _body()
    budget = dict(boolean["budget"])  # type: ignore[arg-type]
    budget["max_api_usd"] = True
    boolean["budget"] = budget
    with pytest.raises(ContractRejected) as money_error:
        load_contract(boolean)
    assert money_error.value.code == "invalid_money"

    number = _body()
    number_budget = dict(number["budget"])  # type: ignore[arg-type]
    number_budget["max_api_usd"] = 1.5
    number["budget"] = number_budget
    with pytest.raises(ContractRejected) as float_error:
        load_contract(number)
    assert float_error.value.code == "invalid_money"

    duplicated = _body()
    duplicated_checks = list(duplicated["acceptance"])  # type: ignore[arg-type]
    duplicated["acceptance"] = [duplicated_checks[0], duplicated_checks[0]]
    with pytest.raises(ContractRejected) as duplicate_error:
        load_contract(duplicated)
    assert duplicate_error.value.code == "duplicate_check_id"


@pytest.mark.parametrize("verifier_type", ["citation-check", "rubric-review"])
def test_r2_runners_are_not_admitted(verifier_type: str) -> None:
    body = _body()
    if verifier_type == "citation-check":
        verifier: dict[str, object] = {
            "type": verifier_type,
            "source_manifest_ref": "sources",
            "claims_ref": "claims",
        }
    else:
        verifier = {
            "type": verifier_type,
            "rubric_ref": "rubric",
            "calibration_set_ref": "examples",
            "reviewer_ref": "owner",
        }
    body["acceptance"] = [
        {
            "id": "AC-LATER",
            "description": "later runner",
            "required": True,
            "verifier": verifier,
            "evidence": {"required": True, "kind": "later-report"},
        }
    ]
    with pytest.raises(ContractRejected) as error:
        load_contract(body)
    assert error.value.code == "runner_not_admitted"


def test_unknown_approval_field_and_restricted_egress_are_rejected() -> None:
    unknown = _body()
    unknown["approved_by"] = "model"
    with pytest.raises(ContractRejected) as unknown_error:
        load_contract(unknown)
    assert unknown_error.value.code == "invalid_contract"
    assert "model" not in str(unknown_error.value)

    current = load_contract(_body())
    opened = current.model_copy(
        update={
            "constraints": current.constraints.model_copy(update={"cloud_egress": "allow"}),
        }
    )
    with pytest.raises(ContractRejected) as egress_error:
        load_contract(json.loads(opened.model_dump_json()))
    assert egress_error.value.code == "egress_denied"
