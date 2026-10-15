"""Read-only static inventory of planned cases; never a release gate evaluator.

Literal source registration is a navigation aid, not execution/assertion proof.
No tests, imports from inspected files, provider calls or effects are executed.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field, ValidationError

CaseId = Annotated[str, Field(pattern=r"^AOS-[0-9]{3}[ab]?-TC[0-9]{2}$")]


class CatalogCase(BaseModel):
    id: CaseId
    planned_nodeid: str
    requires_live_evidence: bool
    status: str


class Catalog(BaseModel):
    roadmap_revision: int
    cases: list[CatalogCase]


class Gate(BaseModel):
    id: str
    required_case_ids: list[CaseId]
    required_case_count: int | None = None
    pretrial_required_case_ids: list[CaseId] | None = None
    trial_and_owner_case_ids: list[CaseId] | None = None


class Gates(BaseModel):
    roadmap_revision: int
    gates: list[Gate]


@dataclass(frozen=True)
class Registration:
    case_id: str
    node_id: str
    live_annotation: bool


@dataclass(frozen=True)
class CaseInventory:
    case_id: str
    catalog_status: str
    planned_node_id: str
    registered_nodes: tuple[str, ...]
    live_nodes: tuple[str, ...]
    requires_live_evidence: bool
    planned_mapping_found: bool
    live_annotation_mismatch: bool


@dataclass(frozen=True)
class Inventory:
    roadmap_revision: int
    gate_id: str
    stage: str
    inventory_status: str
    release_verdict: str
    required_count: int
    registered_count: int
    missing_case_ids: tuple[str, ...]
    mapping_gap_case_ids: tuple[str, ...]
    live_mismatch_case_ids: tuple[str, ...]
    live_required_case_ids: tuple[str, ...]
    unlisted_registration_ids: tuple[str, ...]
    cases: tuple[CaseInventory, ...]


def _live_mark(node: ast.expr) -> bool:
    if isinstance(node, ast.Call):
        node = node.func
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "live"
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "mark"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "pytest"
    )


def _scope_live(nodes: list[ast.stmt]) -> bool:
    for node in nodes:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "pytestmark" for target in node.targets
        ):
            values = node.value.elts if isinstance(node.value, (ast.List, ast.Tuple)) else [node.value]
            if any(_live_mark(value) for value in values):
                return True
    return False


def _literal_cases(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    result: set[str] = set()
    # Do not attribute nested helper/test functions' receipts to their parent.
    pending: list[ast.AST] = list(function.body)
    while pending:
        node = pending.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "record_property"
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "gate_case_id"
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            result.add(node.args[1].value)
        pending.extend(ast.iter_child_nodes(node))
    return result


def registrations(root: Path) -> list[Registration]:
    result: list[Registration] = []
    seen_nodes: set[str] = set()

    def visit(nodes: list[ast.stmt], prefix: str, inherited_live: bool) -> None:
        scope_live = inherited_live or _scope_live(nodes)
        for node in nodes:
            if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                visit(node.body, f"{prefix}::{node.name}", scope_live or any(map(_live_mark, node.decorator_list)))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                node_id = f"{prefix}::{node.name}"
                if node_id in seen_nodes:
                    raise ValueError(f"duplicate_test_node:{node_id}")
                seen_nodes.add(node_id)
                live = scope_live or any(map(_live_mark, node.decorator_list))
                for case_id in sorted(_literal_cases(node)):
                    result.append(Registration(case_id, node_id, live))

    for path in sorted((root / "tests").rglob("test_*.py")):
        # Avoid reading outside the explicitly selected source root via a symlink.
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("test_path_outside_root")
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.relative_to(root).as_posix())
        visit(tree.body, path.relative_to(root).as_posix(), False)
    return result


def _unique(values: list[str], description: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate_{description}")


def build_inventory(root: Path, gate_id: str, *, pretrial: bool = False) -> Inventory:
    catalog = Catalog.model_validate_json((root / "docs/testing/test-catalog.json").read_bytes())
    gates = Gates.model_validate_json((root / "docs/testing/release-gates.json").read_bytes())
    if catalog.roadmap_revision != gates.roadmap_revision:
        raise ValueError("roadmap_revision_mismatch")
    _unique([case.id for case in catalog.cases], "catalog_case")
    _unique([gate.id for gate in gates.gates], "gate")
    selected = next((gate for gate in gates.gates if gate.id == gate_id), None)
    if selected is None:
        raise ValueError("unknown_gate")
    for gate in gates.gates:
        _unique(gate.required_case_ids, "required_case")
        if not gate.required_case_ids:
            raise ValueError("empty_gate")
        if gate.required_case_count is not None and gate.required_case_count != len(gate.required_case_ids):
            raise ValueError("required_case_count_mismatch")
        if gate.pretrial_required_case_ids is not None:
            _unique(gate.pretrial_required_case_ids, "pretrial_case")
            trial = gate.trial_and_owner_case_ids
            if trial is None:
                raise ValueError("missing_trial_partition")
            _unique(trial, "trial_case")
            pre = set(gate.pretrial_required_case_ids)
            if pre & set(trial) or pre | set(trial) != set(gate.required_case_ids):
                raise ValueError("invalid_trial_partition")
    required = selected.pretrial_required_case_ids if pretrial else selected.required_case_ids
    if not required:
        raise ValueError("pretrial_not_available")
    index = {case.id: case for case in catalog.cases}
    if any(case_id not in index for gate in gates.gates for case_id in gate.required_case_ids):
        raise ValueError("required_case_missing_from_catalog")
    registered = registrations(root)
    cases: list[CaseInventory] = []
    for case_id in required:
        case = index[case_id]
        matches = [entry for entry in registered if entry.case_id == case_id]
        live_nodes = tuple(entry.node_id for entry in matches if entry.live_annotation)
        planned_match = any(
            entry.node_id == case.planned_nodeid or entry.node_id.startswith(case.planned_nodeid + "::")
            for entry in matches
        )
        cases.append(
            CaseInventory(
                case_id,
                case.status,
                case.planned_nodeid,
                tuple(entry.node_id for entry in matches),
                live_nodes,
                case.requires_live_evidence or bool(live_nodes),
                planned_match,
                bool(matches) and bool(live_nodes) != case.requires_live_evidence,
            )
        )
    missing = tuple(case.case_id for case in cases if not case.registered_nodes)
    mapping = tuple(case.case_id for case in cases if not case.planned_mapping_found)
    mismatches = tuple(case.case_id for case in cases if case.live_annotation_mismatch)
    unlisted = tuple(sorted({entry.case_id for entry in registered} - index.keys()))
    return Inventory(
        catalog.roadmap_revision,
        gate_id,
        "PRETRIAL" if pretrial else "FINAL",
        "GAPS" if missing or mapping or mismatches or unlisted else "REGISTERED",
        "NOT_EVALUATED",
        len(required),
        sum(bool(case.registered_nodes) for case in cases),
        missing,
        mapping,
        mismatches,
        tuple(case.case_id for case in cases if case.requires_live_evidence),
        unlisted,
        tuple(cases),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--gate", default="G3")
    parser.add_argument("--pretrial", action="store_true")
    args = parser.parse_args()
    try:
        inventory = build_inventory(args.root.resolve(), args.gate, pretrial=args.pretrial)
    except (OSError, ValueError, SyntaxError, ValidationError):
        # Do not echo arbitrary file contents or paths into logs on invalid input.
        print(json.dumps({"inventory_status": "INVALID_INPUT", "release_verdict": "NOT_EVALUATED"}))
        return 2
    report = asdict(inventory)
    head = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=args.root,
        capture_output=True,
        text=True,
        check=False,
    )
    report["inspected_commit"] = head.stdout.strip() if head.returncode == 0 else None
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=args.root,
        capture_output=True,
        text=True,
        check=False,
    )
    report["working_tree_dirty"] = bool(status.stdout.strip()) if status.returncode == 0 else None
    report["catalog_status_counts"] = dict(Counter(case.catalog_status for case in inventory.cases))
    report["limitations"] = (
        "Static literal registrations only; not pytest collection, test execution, assertion coverage, "
        "trusted receipts, live conformance or release acceptance. Dynamic/aliased registrations need manual review."
    )
    print(json.dumps(report, indent=2))
    return 1 if inventory.inventory_status == "GAPS" else 0


if __name__ == "__main__":
    sys.exit(main())
