"""AOS-004-TC01. A scripted worker leaves a candidate, not an accepted result."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from panestria.brokers.harness.mock import OUTPUT_LIMIT, Candidate, MockWorkerAdapter, Observation
from panestria.sandbox.worktree import WorkspaceManifest, WorktreeManager

ROOT = Path(__file__).resolve().parents[2]
SEED = "alpha"


def _properties(record_property: pytest.RecordProperty) -> None:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False)
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, text=True, capture_output=True, check=False)
    record_property("gate_case_id", "AOS-004-TC01")
    record_property("candidate_commit", commit.stdout.strip())
    record_property("fixture_digest", hashlib.sha256(SEED.encode()).hexdigest())
    record_property("lane", "integration")
    record_property("execution_mode", "OS_BOUNDARY")
    record_property("worktree_state", "dirty" if dirty.stdout.strip() else "clean")


def _success(root: Path, attempt_id: str) -> tuple[WorkspaceManifest, Candidate]:
    manifest = WorktreeManager().create(root, attempt_id, SEED)
    adapter = MockWorkerAdapter(manifest, "success", SEED)
    adapter.start()
    return manifest, adapter.collect()


def test_mock_success_and_repeat(record_property: pytest.RecordProperty, tmp_path: Path) -> None:
    _properties(record_property)
    expected = hashlib.sha256(b"edit:alpha\n").hexdigest()
    first_manifest, first = _success(tmp_path / "one", "attempt-a")
    second_manifest, second = _success(tmp_path / "two", "attempt-b")
    assert first.status == "CANDIDATE"
    assert first.accepted is False
    assert first.checks == "NOT_RUN"
    assert first.artifact_sha256 == expected
    assert second.artifact_sha256 == first.artifact_sha256
    assert second.stdout_sha256 == first.stdout_sha256
    assert second.base_sha == first.base_sha
    assert Path(first_manifest.worktree).is_relative_to(tmp_path)
    assert (Path(first_manifest.worktree) / "allowed.txt").read_text() == "edit:alpha\n"

    with pytest.raises(ValueError, match="attempt id"):
        WorktreeManager().create(tmp_path / "bad", "../outside", SEED)

    escaped = WorktreeManager().create(tmp_path / "escape", "attempt-c", SEED)
    bad = MockWorkerAdapter(escaped, "bad_path", SEED)
    bad.start()
    rejected = bad.collect()
    assert rejected.status == "REJECTED"
    assert rejected.accepted is False
    assert (tmp_path / "escape" / "outside.txt").is_file()

    hung_manifest = WorktreeManager().create(tmp_path / "hung", "attempt-d", SEED)
    hung = MockWorkerAdapter(hung_manifest, "hung", SEED)
    hung.start()
    assert hung.observe() == Observation(False, False, True)
    hung.cancel()
    cancelled = hung.observe()
    assert cancelled.cancellation_requested is True
    assert cancelled.terminated is True
    assert cancelled.running is False
    assert hung.collect().status == "CANCELLED"

    crashed_manifest = WorktreeManager().create(tmp_path / "crash", "attempt-e", SEED)
    crashed = MockWorkerAdapter(crashed_manifest, "crash", SEED)
    crashed.start()
    crash_result = crashed.collect()
    assert crash_result.status == "CRASHED"
    assert crash_result.accepted is False

    verbose_manifest = WorktreeManager().create(tmp_path / "verbose", "attempt-f", SEED)
    verbose = MockWorkerAdapter(verbose_manifest, "verbose", SEED)
    verbose.start()
    bounded = verbose.collect()
    assert bounded.truncated is True
    assert bounded.accepted is False
    assert bounded.stdout_sha256 == hashlib.sha256(b"x" * OUTPUT_LIMIT).hexdigest()
