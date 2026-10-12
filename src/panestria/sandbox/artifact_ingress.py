"""Copy a candidate into a store the worker worktree cannot contain."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg

from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.uow import UnitOfWork

_OPEN = frozenset({"PENDING", "RUNNING"})
_TERMINAL_TASK = frozenset({"COMPLETED", "FAILED", "CANCELLED", "REJECTED"})


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
        data, digest = self._read_source(source)
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

    def stage_partial(self, source: Path) -> Path:
        """Write the temporary blob and stop. A crash here leaves no evidence name."""
        data, digest = self._read_source(source)
        temporary = self.store / f".{digest}.partial"
        temporary.write_bytes(data)
        return temporary

    def recheck(self, ref: ArtifactRef) -> bool:
        path = Path(ref.path)
        if path.is_symlink() or not path.is_file():
            return False
        if path.parent.resolve() != self.store or path.name != ref.digest:
            return False
        return hashlib.sha256(path.read_bytes()).hexdigest() == ref.digest

    def record_ref(
        self,
        connection: psycopg.Connection[Any],
        ref: ArtifactRef,
        *,
        artifact_id: str,
        task_id: str,
        attempt_id: str,
        owner_id: str,
        project_id: str,
        kind: str = "candidate",
    ) -> None:
        """Publish one reference and its event. The caller commits. A mismatch is not recorded."""
        self.insert_authorized(
            connection,
            ref,
            artifact_id=artifact_id,
            task_id=task_id,
            attempt_id=attempt_id,
            owner_id=owner_id,
            project_id=project_id,
            kind=kind,
        )
        row = connection.execute("SELECT goal_id::text FROM panestria.task WHERE id = %s", (task_id,)).fetchone()
        if row is None:
            raise ValueError("attempt not found")
        append_event(
            UnitOfWork(connection),
            goal_id=str(row[0]),
            task_id=task_id,
            kind="artifact.published",
            actor=owner_id,
            payload={"artifact_id": artifact_id, "epoch": ref.epoch, "sha256": ref.digest},
        )

    def insert_authorized(
        self,
        connection: psycopg.Connection[Any],
        ref: ArtifactRef,
        *,
        artifact_id: str,
        task_id: str,
        attempt_id: str,
        owner_id: str,
        project_id: str,
        kind: str,
    ) -> None:
        """Lock the current attempt and insert the reference. The caller emits the last event."""
        if not self.recheck(ref):
            raise ValueError("blob does not match the ref")
        row = connection.execute(
            "SELECT attempt.lease_epoch, attempt.status, goal.owner_id::text, goal.project_id::text,"
            " task.state"
            " FROM panestria.task_attempt AS attempt"
            " JOIN panestria.task AS task ON task.id = attempt.task_id"
            " JOIN panestria.goal AS goal ON goal.id = task.goal_id"
            " WHERE attempt.id = %s AND attempt.task_id = %s"
            " FOR UPDATE OF attempt",
            (attempt_id, task_id),
        ).fetchone()
        if row is None:
            raise ValueError("attempt not found")
        epoch, status, owner, project, state = row
        if str(owner) != owner_id or str(project) != project_id or ref.actor != owner_id:
            raise ValueError("scope mismatch")
        if int(epoch) != ref.epoch:
            raise ValueError("stale epoch")
        if str(status) not in _OPEN or str(state) in _TERMINAL_TASK:
            raise ValueError("terminal attempt")
        size = Path(ref.path).stat().st_size
        connection.execute(
            "INSERT INTO panestria.artifact"
            " (id, task_id, attempt_id, kind, store_key, sha256, size_bytes)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (artifact_id, task_id, attempt_id, kind, ref.digest, ref.digest, size),
        )

    def cleanup_orphans(self, referenced: set[str]) -> tuple[str, ...]:
        """Remove partials and unreferenced regular files. Symlinks are left in place."""
        removed: list[str] = []
        for child in self.store.iterdir():
            if child.is_symlink():
                continue
            if child.name.startswith(".") or child.name not in referenced:
                child.unlink()
                removed.append(child.name)
        return tuple(sorted(removed))

    def _read_source(self, source: Path) -> tuple[bytes, str]:
        if source.is_symlink():
            raise ValueError("symlink source")
        resolved = source.resolve()
        if not resolved.is_relative_to(self.worktree):
            raise ValueError("source escapes the worktree")
        data = resolved.read_bytes()
        return data, hashlib.sha256(data).hexdigest()
