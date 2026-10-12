"""Exact worktree diff. Symlinks and off-scope paths fail closed."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_BASELINE = frozenset({".git", "README.txt"})
_RESERVED_ROOT = frozenset({"repo", "attempts", "store", "protected"})


@dataclass(frozen=True)
class DiffReport:
    changed: tuple[str, ...]
    denied: tuple[str, ...]
    ok: bool


def inspect_diff(root: Path, worktree: Path, allowlist: frozenset[str]) -> DiffReport:
    denied: list[str] = []
    changed: list[str] = []
    for child in root.iterdir():
        if child.name not in _RESERVED_ROOT:
            denied.append(child.name)
    for dirpath, dirnames, filenames in os.walk(worktree, followlinks=False):
        dirnames[:] = [name for name in dirnames if name != ".git"]
        for name in filenames:
            path = Path(dirpath) / name
            relative = path.relative_to(worktree).as_posix()
            if path.is_symlink():
                denied.append(relative)
                continue
            if relative in _BASELINE:
                continue
            if relative not in allowlist:
                denied.append(relative)
                continue
            changed.append(relative)
    rejected = tuple(sorted(set(denied)))
    present = tuple(sorted(set(changed)))
    return DiffReport(present, rejected, ok=not rejected and bool(present))
