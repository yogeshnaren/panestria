"""Shared private-state helpers keep the behaviour product stores relied on in the demo."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from panestria.fsutil import LocalStateUnavailable, atomic_write_json, exclusive_lock, private_dir
from panestria_devkit.execution.proposal_demo import DemoUnavailable


def test_private_dir_creates_an_owner_only_directory(tmp_path: Path) -> None:
    target = tmp_path / "state" / "nested"
    assert private_dir(target) == target
    assert target.is_dir() and target.stat().st_mode & 0o777 == 0o700
    assert private_dir(target) == target  # Idempotent on an existing private directory.


def test_private_dir_refuses_a_symlink(tmp_path: Path) -> None:
    (tmp_path / "real").mkdir(mode=0o700)
    (tmp_path / "link").symlink_to(tmp_path / "real")
    with pytest.raises(LocalStateUnavailable, match="^unsafe_demo_root$"):
        private_dir(tmp_path / "link")


@pytest.mark.parametrize("mode", [0o750, 0o705, 0o770])
def test_private_dir_refuses_group_or_other_access(tmp_path: Path, mode: int) -> None:
    target = tmp_path / "shared"
    target.mkdir()
    target.chmod(mode)
    with pytest.raises(LocalStateUnavailable, match="^private_demo_root_required$"):
        private_dir(target)


def test_private_dir_refuses_an_unresolved_path(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir(mode=0o700)
    with pytest.raises(LocalStateUnavailable, match="^private_demo_root_required$"):
        private_dir(tmp_path / "a" / ".." / "a")


def test_atomic_write_json_replaces_with_sorted_json_and_leaves_no_temp(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    target.write_text("old")
    atomic_write_json(target, {"b": 1, "a": [2]})
    assert target.read_text() == json.dumps({"a": [2], "b": 1}, sort_keys=True)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["state.json"]
    assert target.stat().st_mode & 0o077 == 0  # mkstemp creates 0600 and the rename keeps it.


def test_atomic_write_json_leaves_the_old_file_when_encoding_fails(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    target.write_text("old")
    with pytest.raises(TypeError):
        atomic_write_json(target, {"bad": object()})
    assert target.read_text() == "old"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["state.json"]


def test_exclusive_lock_refuses_a_second_holder_and_releases(tmp_path: Path) -> None:
    lock = tmp_path / "operation.lock"
    with exclusive_lock(lock):
        with pytest.raises(LocalStateUnavailable, match="^demo_operation_running$"):
            with exclusive_lock(lock):
                pass
        # A separate open file description in another process sees the same lock.
        pid = os.fork()
        if pid == 0:
            try:
                with exclusive_lock(lock):
                    os._exit(1)
            except LocalStateUnavailable:
                os._exit(0)
            os._exit(2)
        _, status = os.waitpid(pid, 0)
        assert os.waitstatus_to_exitcode(status) == 0
    with exclusive_lock(lock):
        pass


def test_demo_refusals_are_local_state_errors() -> None:
    # Handlers that catch the base class keep catching both, as they did when
    # the helpers raised DemoUnavailable.
    assert issubclass(DemoUnavailable, LocalStateUnavailable)
