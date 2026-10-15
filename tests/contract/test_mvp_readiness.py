"""Manifest drift, missing registrations and live work cannot look accepted."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from panestria.verification.readiness import build_inventory, registrations

ROOT = Path(__file__).resolve().parents[2]


def fixture(root: Path, *, live: bool = False) -> None:
    (root / "docs/testing").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "docs/testing/test-catalog.json").write_text(
        json.dumps(
            {
                "roadmap_revision": 3,
                "cases": [
                    {
                        "id": "AOS-030-TC01",
                        "planned_nodeid": "tests/test_sample.py::test_first",
                        "requires_live_evidence": live,
                        "status": "OBSERVED_PASS",
                    },
                    {
                        "id": "AOS-030-TC04",
                        "planned_nodeid": "tests/test_trial.py",
                        "requires_live_evidence": True,
                        "status": "NOT_RUN",
                    },
                ],
            }
        )
    )
    (root / "docs/testing/release-gates.json").write_text(
        json.dumps(
            {
                "roadmap_revision": 3,
                "gates": [
                    {
                        "id": "G3",
                        "required_case_ids": ["AOS-030-TC01", "AOS-030-TC04"],
                        "required_case_count": 2,
                        "pretrial_required_case_ids": ["AOS-030-TC01"],
                        "trial_and_owner_case_ids": ["AOS-030-TC04"],
                    }
                ],
            }
        )
    )
    (root / "tests/test_sample.py").write_text("""
raise RuntimeError("inspection must not execute this file")
def test_first(record_property):
    record_property("gate_case_id", "AOS-030-TC01")
""")


def test_static_registration_is_not_execution_or_owner_acceptance(tmp_path: Path) -> None:
    fixture(tmp_path)
    pretrial = build_inventory(tmp_path, "G3", pretrial=True)
    assert pretrial.required_count == pretrial.registered_count == 1
    assert pretrial.inventory_status == "REGISTERED"
    assert pretrial.release_verdict == "NOT_EVALUATED"
    final = build_inventory(tmp_path, "G3")
    assert final.required_count == 2 and final.missing_case_ids == ("AOS-030-TC04",)
    assert final.inventory_status == "GAPS" and final.release_verdict == "NOT_EVALUATED"


def test_changed_node_mapping_and_historical_pass_do_not_hide_gap(tmp_path: Path) -> None:
    fixture(tmp_path)
    path = tmp_path / "tests/test_sample.py"
    path.write_text(path.read_text().replace("test_first", "test_relocated"))
    report = build_inventory(tmp_path, "G3", pretrial=True)
    assert not report.missing_case_ids
    assert report.mapping_gap_case_ids == ("AOS-030-TC01",)
    assert report.cases[0].catalog_status == "OBSERVED_PASS"
    assert report.inventory_status == "GAPS"


@pytest.mark.parametrize("scope", ["function", "module", "class"])
def test_live_annotations_cannot_be_downgraded(tmp_path: Path, scope: str) -> None:
    fixture(tmp_path)
    source = """def test_first(record_property):
    record_property("gate_case_id", "AOS-030-TC01")
"""
    if scope == "function":
        source = "@pytest.mark.live\n" + source
    elif scope == "module":
        source = "pytestmark = [pytest.mark.live]\n" + source
    else:
        source = "@pytest.mark.live\nclass TestSuite:\n" + "\n".join("    " + line for line in source.splitlines())
    (tmp_path / "tests/test_sample.py").write_text(source)
    report = build_inventory(tmp_path, "G3", pretrial=True)
    assert report.live_mismatch_case_ids == ("AOS-030-TC01",)
    assert report.live_required_case_ids == ("AOS-030-TC01",)
    assert report.cases[0].live_nodes


def test_catalog_live_requirement_is_retained_without_annotation(tmp_path: Path) -> None:
    fixture(tmp_path, live=True)
    report = build_inventory(tmp_path, "G3", pretrial=True)
    assert report.live_mismatch_case_ids == report.live_required_case_ids == ("AOS-030-TC01",)


@pytest.mark.parametrize("defect", ["duplicate_case", "duplicate_gate", "empty", "count", "partition", "revision"])
def test_invalid_manifests_fail_closed(tmp_path: Path, defect: str) -> None:
    fixture(tmp_path)
    gate_path = tmp_path / "docs/testing/release-gates.json"
    catalog_path = tmp_path / "docs/testing/test-catalog.json"
    gates = json.loads(gate_path.read_text())
    catalog = json.loads(catalog_path.read_text())
    if defect == "duplicate_case":
        catalog["cases"].append(catalog["cases"][0])
    elif defect == "duplicate_gate":
        gates["gates"].append(gates["gates"][0])
    elif defect == "empty":
        gates["gates"][0]["required_case_ids"] = []
    elif defect == "count":
        gates["gates"][0]["required_case_count"] = 124
    elif defect == "partition":
        gates["gates"][0]["pretrial_required_case_ids"].append("AOS-030-TC04")
    elif defect == "revision":
        gates["roadmap_revision"] = 2
    gate_path.write_text(json.dumps(gates))
    catalog_path.write_text(json.dumps(catalog))
    with pytest.raises(ValueError):
        build_inventory(tmp_path, "G3")


def test_nested_receipts_do_not_register_parent_test(tmp_path: Path) -> None:
    fixture(tmp_path)
    (tmp_path / "tests/test_sample.py").write_text("""
def test_first(record_property):
    def helper():
        record_property("gate_case_id", "AOS-030-TC01")
""")
    assert build_inventory(tmp_path, "G3", pretrial=True).missing_case_ids == ("AOS-030-TC01",)


def test_duplicate_test_names_do_not_produce_multiple_fake_receipts(tmp_path: Path) -> None:
    fixture(tmp_path)
    path = tmp_path / "tests/test_sample.py"
    path.write_text(path.read_text() + "\ndef test_first():\n    pass\n")
    with pytest.raises(ValueError, match="duplicate_test_node"):
        registrations(tmp_path)


def test_symlink_source_escape_is_rejected(tmp_path: Path) -> None:
    fixture(tmp_path)
    outside = tmp_path.parent / (tmp_path.name + "_outside.py")
    outside.write_text("raise RuntimeError('not executed')\n")
    try:
        (tmp_path / "tests/test_escape.py").symlink_to(outside)
        with pytest.raises(ValueError, match="outside_root"):
            registrations(tmp_path)
    finally:
        outside.unlink()


def test_revision_three_inventory_includes_all_extensions() -> None:
    final = build_inventory(ROOT, "G3")
    pretrial = build_inventory(ROOT, "G3", pretrial=True)
    assert final.required_count == 157 and pretrial.required_count == 156
    assert {case.case_id for case in final.cases} >= {"AOS-012-TC10", "AOS-028-TC08", "AOS-030-TC04"}
    assert "AOS-030-TC04" not in {case.case_id for case in pretrial.cases}
    assert "AOS-018-TC02" in final.live_required_case_ids
    assert final.release_verdict == "NOT_EVALUATED"


def test_cli_invalid_input_is_bounded_and_never_passes(tmp_path: Path) -> None:
    fixture(tmp_path)
    (tmp_path / "docs/testing/test-catalog.json").write_text("PRIVATE_TEST_SENTINEL invalid JSON")
    run = subprocess.run(
        [sys.executable, "-m", "panestria.verification.readiness", "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 2 and "PRIVATE_TEST_SENTINEL" not in run.stdout + run.stderr
    assert json.loads(run.stdout) == {"inventory_status": "INVALID_INPUT", "release_verdict": "NOT_EVALUATED"}
