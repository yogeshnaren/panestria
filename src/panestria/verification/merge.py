"""Conservative blob-level integration; no checkout, merge drivers or ref writes."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from panestria.verification.candidate import capture_candidate
from panestria.verification.git_snapshot import GitSnapshot, SnapshotRejected, verify_snapshot


@dataclass(frozen=True)
class Conflict:
    path: str
    contributors: tuple[str, ...]


@dataclass(frozen=True)
class IntegratedCandidate:
    candidate: str | None
    conflicts: tuple[Conflict, ...]


def integrate(
    repository: Path,
    base_commit: str,
    base: GitSnapshot,
    workers: tuple[tuple[str, GitSnapshot], ...],
    workspace: Path,
    *,
    deadline: float | None = None,
) -> IntegratedCandidate:
    """Combine distinct file edits/deletions; overlapping edits require owner review.

    Candidates are full snapshots of the same base. Identical edits can be shared.
    Differing edits to any one file stop; even non-overlapping text edits are not
    silently resolved. Protected refs and worker directories are never modified.
    """
    verify_snapshot(base)
    if not 1 <= len(workers) <= 15 or len({identity for identity, _ in workers}) != len(workers):
        raise SnapshotRejected("integration_input_limit")
    if (
        not workspace.is_absolute()
        or workspace.resolve() != workspace
        or workspace.exists()
        or not workspace.parent.is_dir()
        or workspace.parent.stat().st_uid != os.getuid()
        or workspace.parent.stat().st_mode & 0o077
    ):
        raise SnapshotRejected("private_integration_workspace_required")
    original = {entry[0]: entry[1:] for entry in base.files}
    choices = {name: (entry, base.directory / name) for name, entry in original.items()}
    edits: dict[str, list[tuple[str, tuple[str, int, str] | None, Path]]] = {}
    for identity, snapshot in workers:
        verify_snapshot(snapshot)
        current = {entry[0]: entry[1:] for entry in snapshot.files}
        changed = tuple(
            sorted(name for name in original.keys() | current.keys() if original.get(name) != current.get(name))
        )
        if changed != snapshot.changed_paths:
            raise SnapshotRejected("integration_base_diff_mismatch")
        for name in changed:
            edits.setdefault(name, []).append((identity, current.get(name), snapshot.directory / name))
    conflicts = [
        Conflict(name, tuple(identity for identity, _, _ in changes))
        for name, changes in sorted(edits.items())
        if len({entry for _, entry, _ in changes}) > 1
    ]
    for name, changes in edits.items():
        _, entry, source = changes[0]
        if entry is None:
            choices.pop(name, None)
        else:
            choices[name] = (entry, source)
    # Distinct changes can conflict structurally (file vs directory) as well.
    for name in sorted(choices):
        if any(name.startswith(other + "/") for other in choices if other != name):
            conflicts.append(Conflict(name, tuple(identity for identity, _ in workers)))
    if conflicts:
        return IntegratedCandidate(None, tuple(conflicts))
    workspace.mkdir(mode=0o700)
    for name, (entry, source) in sorted(choices.items()):
        target = workspace / name
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target.write_bytes(source.read_bytes())
        target.chmod(0o700 if entry[2] == "100755" else 0o600)
    candidate = capture_candidate(repository, base_commit, workspace, deadline=deadline)
    return IntegratedCandidate(candidate, ())
