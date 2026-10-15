"""Snapshot creation uses raw Git blobs; attributes cannot execute checkout filters."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from panestria.verification.git_snapshot import SnapshotRejected, materialize, verify_snapshot


def test_raw_blobs_ignore_checkout_filters_and_detect_later_changes(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}

    def git(*args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(source), "-c", "core.hooksPath=/dev/null", *args], env=env, text=True
        ).strip()

    git("init", "-b", "main")
    git("config", "user.name", "Synthetic snapshot test")
    git("config", "user.email", "synthetic@panestria.invalid")
    (source / "answer.txt").write_text("base")
    (source / ".gitattributes").write_text("answer.txt filter=poison\n")
    git("add", "answer.txt", ".gitattributes")
    git("commit", "-m", "synthetic base")
    base = git("rev-parse", "HEAD")
    (source / "answer.txt").write_text("candidate bytes")
    git("commit", "-am", "synthetic candidate")
    candidate = git("rev-parse", "HEAD")
    bare = tmp_path / "protected.git"
    subprocess.run(["git", "clone", "--bare", str(source), str(bare)], check=True, capture_output=True, env=env)
    sentinel = tmp_path / "filter-executed"
    subprocess.run(
        ["git", "--git-dir", str(bare), "config", "filter.poison.smudge", f"touch {sentinel}"], check=True, env=env
    )
    snapshot = materialize(bare, base, candidate, tmp_path / "snapshots" / "one")
    assert snapshot.changed_paths == ("answer.txt",)
    assert (snapshot.directory / "answer.txt").read_text() == "candidate bytes"
    assert not sentinel.exists() and not (snapshot.directory / ".git").exists()
    verify_snapshot(snapshot)
    path = snapshot.directory / "answer.txt"
    path.chmod(0o600)
    path.write_text("corrupted after snapshot")
    with pytest.raises(SnapshotRejected, match="snapshot_changed"):
        verify_snapshot(snapshot)
