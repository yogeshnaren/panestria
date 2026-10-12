"""Scoped artifact reads. A mismatched hash is not accepted evidence."""

from __future__ import annotations

import hashlib
from pathlib import Path

from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork


class ArtifactView:
    def __init__(
        self,
        artifact_id: str,
        kind: str,
        sha256: str,
        size_bytes: int,
        verdicts: list[tuple[str, str]],
    ) -> None:
        self.artifact_id = artifact_id
        self.kind = kind
        self.sha256 = sha256
        self.size_bytes = size_bytes
        self.verdicts = verdicts


class ArtifactService:
    def read(self, uow: UnitOfWork, actor: Actor, artifact_id: str, sandbox_root: Path) -> ArtifactView:
        row = uow.execute(
            "SELECT artifact.kind, artifact.sha256, artifact.size_bytes, task.goal_id::text"
            " FROM panestria.artifact AS artifact"
            " JOIN panestria.task AS task ON task.id = artifact.task_id"
            " JOIN panestria.goal AS goal ON goal.id = task.goal_id"
            " WHERE artifact.id = %s AND goal.owner_id = %s AND goal.project_id = %s",
            (artifact_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        kind, digest, size_bytes, goal_id = row
        stored = str(digest).strip()
        store = (sandbox_root / str(goal_id) / "store").resolve()
        path = (store / stored).resolve()
        if path.parent != store or path.name != stored or not path.is_file():
            raise KernelDenied("missing_evidence")
        data = path.read_bytes()
        if len(data) != int(size_bytes) or hashlib.sha256(data).hexdigest() != stored:
            raise KernelDenied("corrupt_artifact")
        verdicts = uow.execute(
            "SELECT acceptance_check.check_key, check_run.verdict"
            " FROM panestria.check_run AS check_run"
            " JOIN panestria.acceptance_check AS acceptance_check"
            " ON acceptance_check.id = check_run.acceptance_check_id"
            " WHERE check_run.evidence_artifact_id = %s"
            " ORDER BY acceptance_check.check_key",
            (artifact_id,),
        ).fetchall()
        return ArtifactView(
            artifact_id,
            str(kind),
            stored,
            int(size_bytes),
            [(str(check_key), str(verdict)) for check_key, verdict in verdicts],
        )
