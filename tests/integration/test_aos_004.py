"""AOS-004 worker candidate and independent checks."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from panestria.brokers.harness.mock import OUTPUT_LIMIT, Candidate, MockWorkerAdapter, Observation
from panestria.sandbox.artifact_ingress import ArtifactIngress
from panestria.sandbox.worktree import WorkspaceManifest, WorktreeManager
from panestria.verification.artifacts import decide
from panestria.verification.diff import inspect_diff
from panestria.verification.registry import CommandRegistry
from panestria.verification.runner import TrustedCheckRunner

ROOT = Path(__file__).resolve().parents[2]
SEED = "alpha"


REQUIRED_SCRIPT = """\
import os
import sys
from pathlib import Path

if os.environ.get("PANESTRIA_SECRET"):
    raise SystemExit(3)
data = Path(os.environ["PANESTRIA_CANDIDATE"]).read_bytes()
if data.startswith(b"edit:") and data.endswith(b"\\n"):
    raise SystemExit(0)
raise SystemExit(1)
"""

ALLOWLIST = frozenset({"allowed.txt"})


def _properties(record_property: pytest.RecordProperty, case_id: str, lane: str) -> None:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False)
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, text=True, capture_output=True, check=False)
    record_property("gate_case_id", case_id)
    record_property("candidate_commit", commit.stdout.strip())
    record_property("fixture_digest", hashlib.sha256(SEED.encode()).hexdigest())
    record_property("lane", lane)
    record_property("execution_mode", "OS_BOUNDARY")
    record_property("worktree_state", "dirty" if dirty.stdout.strip() else "clean")


def _success(root: Path, attempt_id: str) -> tuple[WorkspaceManifest, Candidate]:
    manifest = WorktreeManager().create(root, attempt_id, SEED)
    adapter = MockWorkerAdapter(manifest, "success", SEED)
    adapter.start()
    return manifest, adapter.collect()


def test_mock_success_and_repeat(record_property: pytest.RecordProperty, tmp_path: Path) -> None:
    _properties(record_property, "AOS-004-TC01", "integration")
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


def _bundle(root: Path) -> CommandRegistry:
    protected = root / "protected"
    protected.mkdir(parents=True)
    (protected / "required_check.py").write_text(REQUIRED_SCRIPT)
    return CommandRegistry.load(protected, sys.executable)


def test_bad_path_and_tampered_checks(
    record_property: pytest.RecordProperty,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _properties(record_property, "AOS-004-TC02", "security")
    monkeypatch.setenv("PANESTRIA_SECRET", "synthetic-sentinel")
    root = tmp_path / "checked"
    registry = _bundle(root)
    manifest, candidate = _success(root, "attempt-ok")
    report = inspect_diff(Path(manifest.root), Path(manifest.worktree), ALLOWLIST)
    assert report.ok is True
    assert report.changed == ("allowed.txt",)
    published = ArtifactIngress(root / "store", Path(manifest.worktree)).finalize(
        Path(manifest.worktree) / "allowed.txt",
        "synthetic-owner",
        1,
    )
    assert published.digest == candidate.artifact_sha256
    assert not Path(published.path).resolve().is_relative_to(Path(manifest.worktree))
    command = registry.resolve("synthetic-required")
    assert command.argv[0] == sys.executable
    assert Path(command.argv[-1]).is_relative_to(root / "protected")
    result = TrustedCheckRunner(registry).run("synthetic-required", Path(published.path), 5)
    assert result.verdict == "PASS"
    assert decide(report, (result,), ("synthetic-required",), True).verdict == "PASS"

    (Path(manifest.worktree) / "other.txt").write_text("off-scope\n")
    off_scope = inspect_diff(Path(manifest.root), Path(manifest.worktree), ALLOWLIST)
    assert off_scope.ok is False
    assert "other.txt" in off_scope.denied
    assert decide(off_scope, (result,), ("synthetic-required",), True).verdict == "FAIL"

    escaped = WorktreeManager().create(tmp_path / "escape", "attempt-escape", SEED)
    outside = MockWorkerAdapter(escaped, "bad_path", SEED)
    outside.start()
    assert outside.collect().status == "REJECTED"
    escaped_diff = inspect_diff(Path(escaped.root), Path(escaped.worktree), ALLOWLIST)
    assert escaped_diff.ok is False
    assert "outside.txt" in escaped_diff.denied

    linked = WorktreeManager().create(tmp_path / "link", "attempt-link", SEED)
    target = tmp_path / "secret-target.txt"
    target.write_text("edit:alpha\n")
    allowed = Path(linked.worktree) / "allowed.txt"
    allowed.symlink_to(target)
    linked_diff = inspect_diff(Path(linked.root), Path(linked.worktree), ALLOWLIST)
    assert linked_diff.ok is False
    assert "allowed.txt" in linked_diff.denied
    with pytest.raises(ValueError, match="symlink"):
        ArtifactIngress(tmp_path / "link" / "store", Path(linked.worktree)).finalize(allowed, "synthetic-owner", 1)
    assert TrustedCheckRunner(registry).run("synthetic-required", allowed, 5).reason == "symlink"

    (Path(manifest.worktree) / "always_pass.py").write_text("raise SystemExit(0)\n")
    with pytest.raises(PermissionError, match="always_pass"):
        registry.add_worker_command("always_pass", (sys.executable, str(Path(manifest.worktree) / "always_pass.py")))
    with pytest.raises(KeyError, match="always_pass"):
        registry.resolve("always_pass")
    assert tuple(item.ref for item in registry.required()) == ("synthetic-required",)

    script = root / "protected" / "required_check.py"
    script.write_text("from pathlib import Path\nPath('ran.txt').write_text('x')\nraise SystemExit(0)\n")
    tampered = TrustedCheckRunner(registry).run("synthetic-required", Path(published.path), 5)
    assert tampered.verdict == "FAIL"
    assert tampered.reason == "bundle_tampered"
    assert not (root / "protected" / "ran.txt").exists()
    assert decide(report, (tampered,), ("synthetic-required",), True).verdict == "FAIL"
