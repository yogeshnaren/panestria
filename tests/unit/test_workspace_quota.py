"""SEC-M1 workspace quota: profile identity, measurement and capped ingress."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import panestria.sandbox.runner as runner
from panestria.sandbox.artifact_ingress import ArtifactIngress
from panestria.sandbox.profiles import DEFAULT_WORKSPACE_BYTES, SandboxProfile, SandboxRejected
from panestria.sandbox.runner import DockerSandbox, workspace_usage


def test_sec_m1_default_quota_keeps_historical_profile_digest():
    assert SandboxProfile().sha256() == SandboxProfile(workspace_bytes=DEFAULT_WORKSPACE_BYTES).sha256()
    assert SandboxProfile(workspace_bytes=2 * 1024**2).sha256() != SandboxProfile().sha256()


@pytest.mark.parametrize("value", [0, 1024**2 - 1, 16 * 1024**3 + 1, True, 2.0 * 1024**2])
def test_sec_m1_quota_bounds_fail_closed(value):
    with pytest.raises(SandboxRejected, match="invalid_workspace_cap"):
        SandboxProfile(workspace_bytes=value).validate()


def test_sec_m1_usage_counts_regular_files_without_following_links(tmp_path):
    (tmp_path / "nested").mkdir()
    (tmp_path / "a").write_bytes(b"x" * 10)
    (tmp_path / "nested" / "b").write_bytes(b"y" * 5)
    outside = tmp_path.parent / (tmp_path.name + "-outside")
    outside.mkdir()
    (outside / "large").write_bytes(b"z" * 1000)
    (tmp_path / "link").symlink_to(outside, target_is_directory=True)
    assert workspace_usage(tmp_path) == 15


def test_sec_m1_unmeasurable_workspace_counts_as_over(tmp_path, monkeypatch):
    for index in range(4):
        (tmp_path / str(index)).write_bytes(b"")
    monkeypatch.setattr(runner, "MAX_WORKSPACE_ENTRIES", 3)
    assert workspace_usage(tmp_path) is None
    monkeypatch.undo()
    real = os.scandir

    def denied(path):
        if Path(path) != tmp_path:
            raise PermissionError(path)
        return real(path)

    (tmp_path / "private").mkdir()
    monkeypatch.setattr(runner.os, "scandir", denied)
    assert workspace_usage(tmp_path) is None


def test_sec_m1_over_quota_workspace_is_refused_before_any_container(tmp_path, monkeypatch):
    root = tmp_path / "attempts"
    worker = root / "worker"
    worker.mkdir(parents=True)
    (worker / "data").write_bytes(b"x" * (1024**2 + 1))

    def forbidden(*_args, **_kwargs):
        raise AssertionError("must not reach the container runtime")

    monkeypatch.setattr(DockerSandbox, "_docker", forbidden)
    with pytest.raises(SandboxRejected, match="workspace_quota_exceeded"):
        DockerSandbox(root).run(
            worker, ("/usr/local/bin/python", "-c", "pass"), SandboxProfile(workspace_bytes=1024**2)
        )


def test_sec_m1_ingress_refuses_oversized_and_special_sources(tmp_path):
    worktree, store = tmp_path / "worktree", tmp_path / "store"
    worktree.mkdir()
    ingress = ArtifactIngress(store, worktree, max_bytes=8)
    (worktree / "ok").write_bytes(b"12345678")
    assert ingress.finalize(worktree / "ok", "owner", 1).digest
    (worktree / "big").write_bytes(b"123456789")
    with pytest.raises(ValueError, match="artifact_too_large"):
        ingress.finalize(worktree / "big", "owner", 1)
    os.mkfifo(worktree / "pipe")
    with pytest.raises(ValueError, match="not a regular file"):
        ingress.finalize(worktree / "pipe", "owner", 1)
    with pytest.raises(ValueError, match="not a regular file"):
        ingress.finalize(worktree, "owner", 1)
    assert sorted(path.name for path in store.iterdir()) == [ingress.finalize(worktree / "ok", "o", 1).digest]


@pytest.mark.parametrize("value", [0, 256 * 1024**2 + 1, True])
def test_sec_m1_ingress_limit_is_bounded(tmp_path, value):
    with pytest.raises(ValueError, match="invalid artifact size limit"):
        ArtifactIngress(tmp_path / "store", tmp_path / "worktree", max_bytes=value)
