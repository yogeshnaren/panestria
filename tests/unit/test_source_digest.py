"""Cached source digest keeps the attestation bytes and still sees every edit."""

import hashlib
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from panestria.execution import source_digest
from panestria.execution.native_build import runtime_versions
from panestria.execution.source_digest import source_sha256


def _reference(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(str(path.relative_to(root)).encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()


def _later(monkeypatch: pytest.MonkeyPatch) -> None:
    # ctime cannot be backdated, so the helper reads after the racy window.
    offset = 10 * source_digest._RACY_NANOSECONDS
    monkeypatch.setattr(source_digest, "time", SimpleNamespace(time_ns=lambda: time.time_ns() + offset))


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "a.py").write_bytes(b"value = 1\n")
    (tmp_path / "pkg" / "b.py").write_bytes(b"value = 2\n")
    (tmp_path / "notes.txt").write_bytes(b"not hashed\n")
    return tmp_path


def test_installed_source_digest_matches_the_original_algorithm():
    root = Path(source_digest.__file__).resolve().parents[1]
    assert runtime_versions()["source_sha256"] == _reference(root)


def test_unchanged_tree_is_not_reread(tree, monkeypatch):
    _later(monkeypatch)
    expected = _reference(tree)
    assert source_sha256(tree) == expected
    reads: list[Path] = []
    original = Path.read_bytes
    monkeypatch.setattr(Path, "read_bytes", lambda self: reads.append(self) or original(self))
    assert source_sha256(tree) == expected
    assert reads == []


@pytest.mark.parametrize("change", ["same_size_edit", "added", "removed"])
def test_any_source_change_changes_the_digest(tree, change, monkeypatch):
    _later(monkeypatch)
    before = source_sha256(tree)
    if change == "same_size_edit":
        (tree / "a.py").write_bytes(b"value = 9\n")
    elif change == "added":
        (tree / "pkg" / "c.py").write_bytes(b"")
    else:
        (tree / "pkg" / "b.py").unlink()
    after = source_sha256(tree)
    assert after != before and after == _reference(tree)


def test_racily_clean_tree_is_never_cached(tree, monkeypatch):
    # A rewrite within one coarse timestamp tick may not change the stat
    # signature, so files modified near the read are hashed on every call.
    assert source_sha256(tree) == _reference(tree)
    assert tree not in source_digest._cache
    _later(monkeypatch)
    source_sha256(tree)
    assert tree in source_digest._cache
