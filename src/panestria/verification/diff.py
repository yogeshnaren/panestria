"""Diff a pinned Git base against the candidate worktree. Unchanged baseline files stay quiet."""

from __future__ import annotations

import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

from panestria.sandbox.gitcmd import allow_git
from panestria.verification.paths import path_permitted

_RESERVED_ROOT = frozenset({"repo", "attempts", "store", "protected"})


@dataclass(frozen=True)
class DiffReport:
    changed: tuple[str, ...]
    denied: tuple[str, ...]
    ok: bool
    base_sha: str = ""
    candidate_tree: str = ""


def inspect_diff(
    root: Path,
    worktree: Path,
    allowlist: frozenset[str],
    *,
    base_sha: str | None = None,
    forbidden: frozenset[str] = frozenset(),
    also_allowed: frozenset[str] | None = None,
) -> DiffReport:
    denied: list[str] = []
    for child in root.iterdir():
        if child.name not in _RESERVED_ROOT:
            denied.append(child.name)
    base, tree, changed, unsafe = _git_changes(worktree, base_sha)
    if base == "":
        denied.append("<not-a-git-tree>")
    for relative in sorted(changed):
        if relative in unsafe or not path_permitted(relative, allowlist, forbidden, also_allowed=also_allowed):
            denied.append(relative)
    rejected = tuple(sorted(set(denied)))
    present = tuple(sorted(path for path in changed if path not in rejected))
    return DiffReport(present, rejected, ok=not rejected and bool(present), base_sha=base, candidate_tree=tree)


def _git_changes(worktree: Path, base_sha: str | None) -> tuple[str, str, set[str], set[str]]:
    if not (worktree / ".git").exists():
        return "", "", set(), set()
    base_text = _git(worktree, ["rev-parse", base_sha or "HEAD"])
    tree_text = _git(worktree, ["rev-parse", "HEAD"])
    if base_text is None or tree_text is None:
        return "", "", set(), set()
    base = base_text.strip()
    tree = tree_text.strip()
    raw = _git(worktree, ["diff", "--raw", "--find-renames", "--no-abbrev", base])
    cached = _git(worktree, ["diff", "--cached", "--raw", "--find-renames", "--no-abbrev", base])
    others_text = _git(worktree, ["ls-files", "--others", "--exclude-standard"])
    if raw is None or cached is None or others_text is None or base == "" or tree == "":
        return "", "", set(), set()
    changed: set[str] = set()
    unsafe: set[str] = set()
    _record_raw(raw, changed, unsafe)
    _record_raw(cached, changed, unsafe)
    for name in others_text.splitlines():
        if not name:
            continue
        changed.add(name)
        if _unexpected_permission(worktree / name):
            unsafe.add(name)
    _collect_new_symlinks(worktree, base, changed, unsafe)
    return base, tree, changed, unsafe


def _record_raw(raw: str, changed: set[str], unsafe: set[str]) -> None:
    for line in raw.splitlines():
        meta, separator, paths = line.partition("\t")
        if separator == "" or not meta.startswith(":"):
            continue
        fields = meta.split()
        new_mode = fields[1] if len(fields) > 1 else ""
        names = [name for name in paths.split("\t") if name]
        changed.update(names)
        if new_mode not in {"100644", "000000"}:
            unsafe.update(names)


def _collect_new_symlinks(worktree: Path, base: str, changed: set[str], unsafe: set[str]) -> None:
    for dirpath, dirnames, filenames in os.walk(worktree, followlinks=False):
        current = Path(dirpath)
        if current.name == ".git" or ".git" in current.relative_to(worktree).parts:
            dirnames.clear()
            continue
        for name in list(dirnames):
            path = current / name
            if not path.is_symlink():
                continue
            relative = path.relative_to(worktree).as_posix()
            dirnames.remove(name)
            if _same_as_base(worktree, base, relative):
                continue
            changed.add(relative)
            unsafe.add(relative)
        for name in filenames:
            path = current / name
            if name == ".git" or not path.is_symlink():
                continue
            relative = path.relative_to(worktree).as_posix()
            if _same_as_base(worktree, base, relative):
                continue
            changed.add(relative)
            unsafe.add(relative)


def _unexpected_permission(path: Path) -> bool:
    """A changed path must be a regular file without an execute bit."""
    try:
        info = path.lstat()
    except OSError:
        return True
    if not stat.S_ISREG(info.st_mode):
        return True
    return bool(info.st_mode & 0o111)


def _same_as_base(worktree: Path, base: str, relative: str) -> bool:
    probe = _git_run(worktree, ["cat-file", "-e", f"{base}:{relative}"])
    if probe is None or probe.returncode != 0:
        return False
    diff = _git_run(worktree, ["diff", "--raw", "--no-abbrev", base, "--", relative])
    return diff is not None and diff.returncode == 0 and diff.stdout.strip() == ""


def _git(worktree: Path, args: list[str]) -> str | None:
    completed = _git_run(worktree, args)
    if completed is None or completed.returncode != 0:
        return None
    return completed.stdout


def _git_run(worktree: Path, args: list[str]) -> subprocess.CompletedProcess[str] | None:
    command = ["git", "-C", str(worktree), *args]
    try:
        allow_git(command)
        return subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return None
