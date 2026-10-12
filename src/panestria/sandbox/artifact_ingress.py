"""Copy a candidate into a store the worker worktree cannot contain."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ArtifactRef:
    digest: str
    path: str
    epoch: int
    actor: str


class ArtifactIngress:
    def __init__(self, store: Path, worktree: Path) -> None:
        self.store = store.resolve()
        self.worktree = worktree.resolve()
        if self.store.is_relative_to(self.worktree):
            raise ValueError("artifact store is inside the worker worktree")
        self.store.mkdir(parents=True, exist_ok=True)

    def finalize(self, source: Path, actor: str, epoch: int) -> ArtifactRef:
        if not actor or epoch < 0:
            raise ValueError("actor and epoch are required")
        if source.is_symlink():
            raise ValueError("symlink source")
        resolved = source.resolve()
        if not resolved.is_relative_to(self.worktree):
            raise ValueError("source escapes the worktree")
        data = resolved.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        temporary = self.store / f".{digest}.partial"
        target = self.store / digest
        temporary.write_bytes(data)
        os.replace(temporary, target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            target.unlink(missing_ok=True)
            raise ValueError("hash mismatch")
        if target.resolve().is_relative_to(self.worktree):
            target.unlink(missing_ok=True)
            raise ValueError("published inside the worktree")
        return ArtifactRef(digest, str(target), epoch, actor)
