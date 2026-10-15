"""Actual Git transactions and effect witnesses are independent of worker narrative."""

from __future__ import annotations

import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from panestria.execution.outbox import Confirmed, NoEffect
from panestria.execution.protected_merge import MergeSpec, ProtectedGitTarget
from panestria.kernel.effects import DispatchClaim


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), "-c", "core.hooksPath=/dev/null", *args], text=True).strip()


def test_atomic_merge_witness_and_lost_response(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-b", "main")
    _git(source, "config", "user.name", "Synthetic verifier fixture")
    _git(source, "config", "user.email", "synthetic@panestria.invalid")
    (source / "code.txt").write_text("base")
    _git(source, "add", "code.txt")
    _git(source, "commit", "-m", "synthetic base")
    base = _git(source, "rev-parse", "HEAD")
    (source / "code.txt").write_text("candidate")
    _git(source, "commit", "-am", "synthetic candidate")
    candidate, tree = _git(source, "rev-parse", "HEAD"), _git(source, "rev-parse", "HEAD^{tree}")
    protected = tmp_path / "protected"
    protected.mkdir()
    bare = protected / "destination.git"
    subprocess.run(["git", "clone", "--bare", str(source), str(bare)], check=True, capture_output=True)
    subprocess.run(["git", "--git-dir", str(bare), "update-ref", "refs/heads/main", base], check=True)
    spec = MergeSpec("refs/heads/main", base, candidate, tree, "ab" * 32)
    target = ProtectedGitTarget(protected, bare, lambda _claim: spec, lambda _claim: spec)
    claim = DispatchClaim(
        str(uuid4()),
        str(uuid4()),
        1,
        f"refs/heads/main@{candidate}",
        "approval:" + str(uuid4()),
        "cd" * 32,
        "reconcile-by-query",
    )
    assert isinstance(target.query(claim), NoEffect)
    target.dispatch(claim)
    assert isinstance(target.query(claim), Confirmed)
    # Repeating the same external operation fails instead of moving a ref twice.
    with pytest.raises(ValueError, match="protected_git_operation_failed"):
        target.dispatch(claim)
    assert isinstance(target.query(claim), Confirmed)
    changed = MergeSpec(spec.destination, base, candidate, base, spec.evidence_sha256)
    wrong = ProtectedGitTarget(protected, bare, lambda _claim: changed, lambda _claim: changed)
    with pytest.raises(ValueError, match="candidate_tree_mismatch"):
        wrong.dispatch(claim)
