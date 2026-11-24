"""Main reuses PR evidence only when no lane deferred a regression."""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"tools/{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


proof = _load("ci_merge_proof")
ci_tests = _load("ci_tests")


def _artifact(files: dict[str, object]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for name, body in files.items():
            bundle.writestr(name, json.dumps(body) if not isinstance(body, str) else body)
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("selection", "reusable"),
    [
        ({"profile": "full", "deferred": []}, True),
        ({"profile": "required", "deferred": []}, True),
        ({"profile": "required", "deferred": [{"node": "tests/x.py::test_a"}]}, False),
        ({"profile": "mutation-witness-only", "deferred": None}, False),
        ({}, False),
    ],
)
def test_only_lanes_that_deferred_nothing_permit_reuse(selection: dict[str, object], reusable: bool) -> None:
    assert proof.selection_permits_reuse(selection) is reusable


def test_selection_is_read_from_the_lane_artifact() -> None:
    archive = _artifact({"ci-kernel.xml": "<testsuite/>", "ci-kernel-selection.json": {"profile": "full"}})
    assert proof.selection_from_artifact(archive, "kernel") == {"profile": "full"}


@pytest.mark.parametrize(
    "files", [{"ci-kernel.xml": "<x/>"}, {"a/ci-kernel-selection.json": {}, "ci-kernel-selection.json": {}}]
)
def test_missing_or_ambiguous_selection_is_rejected(files: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="selection_missing"):
        proof.selection_from_artifact(_artifact(files), "kernel")


def test_required_profile_with_base_equal_to_head_runs_everything() -> None:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    assert ci_tests.deferred_nodes("required", head) == ([], "base_is_head_full_fallback", None)


def _jobs(*extra: dict[str, object]) -> list[dict[str, object]]:
    passed = [{"name": name, "status": "completed", "conclusion": "success"} for name in sorted(proof.REQUIRED)]
    return [*passed, *extra]


@pytest.mark.parametrize(
    ("jobs", "passed"),
    [
        (_jobs(), True),
        (_jobs({"name": "nightly-failure-issue", "status": "completed", "conclusion": "skipped"}), True),
        # A schedule-only job that ran is not PR evidence; nor is any extra or missing job.
        (_jobs({"name": "nightly-failure-issue", "status": "completed", "conclusion": "success"}), False),
        (_jobs({"name": "unknown", "status": "completed", "conclusion": "skipped"}), False),
        (_jobs()[1:], False),
        ([{**_jobs()[0], "conclusion": "skipped"}, *_jobs()[1:]], False),
    ],
)
def test_only_the_exact_required_jobs_passing_permit_reuse(jobs: list[dict[str, object]], passed: bool) -> None:
    assert proof.required_jobs_passed(jobs) is passed
