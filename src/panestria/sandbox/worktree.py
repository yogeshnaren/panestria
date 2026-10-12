"""Create a toy repository and one attempt worktree inside a caller-owned root."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

_ATTEMPT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_OWNER = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_GIT_ENV = {
    "GIT_AUTHOR_NAME": "panestria-synthetic",
    "GIT_AUTHOR_EMAIL": "synthetic@panestria.invalid",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
    "GIT_COMMITTER_NAME": "panestria-synthetic",
    "GIT_COMMITTER_EMAIL": "synthetic@panestria.invalid",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
}


@dataclass(frozen=True)
class WorkspaceManifest:
    root: str
    repo: str
    worktree: str
    base_sha: str
    attempt_id: str
    owner: str = "synthetic-owner"
    ttl_seconds: int = 3600
    created_at: int = 0
    disk_bytes: int = 0


@dataclass(frozen=True)
class CleanupReport:
    attempt_id: str
    outcome: str
    owner: str
    disk_bytes: int
    reason: str


class WorktreeManager:
    def create(
        self,
        root: Path,
        attempt_id: str,
        seed: str,
        *,
        owner: str = "synthetic-owner",
        ttl_seconds: int = 3600,
        now: int = 0,
    ) -> WorkspaceManifest:
        """Build the fixture under root. A user-supplied absolute path is not a root."""
        if not _ATTEMPT_ID.fullmatch(attempt_id):
            raise ValueError("attempt id is not a sandbox name")
        if not _OWNER.fullmatch(owner) or not 1 <= ttl_seconds <= 86400 or now < 0:
            raise ValueError("worktree record is not valid")
        base = root.resolve()
        repo = base / "repo"
        worktree = base / "attempts" / attempt_id
        if not worktree.is_relative_to(base):
            raise ValueError("attempt path escapes the sandbox")
        repo.mkdir(parents=True)
        worktree.parent.mkdir(parents=True)
        env = os.environ.copy()
        env.update(_GIT_ENV)
        self._git(["init", "-b", "main", str(repo)], env)
        self._git(["-C", str(repo), "config", "user.name", _GIT_ENV["GIT_AUTHOR_NAME"]], env)
        self._git(["-C", str(repo), "config", "user.email", _GIT_ENV["GIT_AUTHOR_EMAIL"]], env)
        self._git(["-C", str(repo), "config", "core.hooksPath", "/dev/null"], env)
        (repo / "README.txt").write_text(f"base:{seed}\n")
        self._git(["-C", str(repo), "add", "README.txt"], env)
        self._git(["-C", str(repo), "-c", "core.hooksPath=/dev/null", "commit", "-m", "synthetic-base"], env)
        sha = self._git(["-C", str(repo), "rev-parse", "HEAD"], env).strip()
        self._git(["-C", str(repo), "worktree", "add", "--detach", str(worktree), sha], env)
        disk_bytes = _disk_bytes(worktree)
        manifest = WorkspaceManifest(
            str(base),
            str(repo),
            str(worktree),
            sha,
            attempt_id,
            owner,
            ttl_seconds,
            now,
            disk_bytes,
        )
        _write_record(base, manifest)
        return manifest

    def cleanup(
        self,
        root: Path,
        *,
        now: int,
        live_attempts: set[str],
        store: Path | None = None,
    ) -> tuple[CleanupReport, ...]:
        """Remove expired and unrecorded attempt directories without following symlinks."""
        base = root.resolve()
        attempts = base / "attempts"
        records = _read_records(base)
        names = set(records)
        if attempts.is_dir() and not attempts.is_symlink():
            names.update(child.name for child in attempts.iterdir())
        reports: list[CleanupReport] = []
        for attempt_id in sorted(names):
            reports.append(
                self._cleanup_one(base, attempt_id, records.get(attempt_id), now, live_attempts, store)
            )
        return tuple(reports)

    def _cleanup_one(
        self,
        root: Path,
        attempt_id: str,
        record: dict[str, object] | None,
        now: int,
        live_attempts: set[str],
        store: Path | None,
    ) -> CleanupReport:
        owner = str(record.get("owner", "")) if record else ""
        recorded_disk = record.get("disk_bytes") if record else None
        disk_bytes = recorded_disk if isinstance(recorded_disk, int) else 0
        path = root / "attempts" / attempt_id
        if not _ATTEMPT_ID.fullmatch(attempt_id):
            return CleanupReport(attempt_id, "denied", owner, disk_bytes, "unsafe-name")
        if not path.exists() and not path.is_symlink():
            return CleanupReport(attempt_id, "absent", owner, disk_bytes, "missing")
        if path.is_symlink() or not path.is_dir():
            if _within_ttl(record, now, attempt_id, live_attempts):
                return CleanupReport(attempt_id, "retained", owner, disk_bytes, "live")
            if path.is_symlink() and not path.parent.resolve().is_relative_to(root):
                return CleanupReport(attempt_id, "denied", owner, disk_bytes, "symlink-escape")
            path.unlink()
            _drop_record(root, attempt_id)
            report = CleanupReport(attempt_id, "removed", owner, disk_bytes, "unlinked-symlink")
            _publish(store, report)
            return report
        if _within_ttl(record, now, attempt_id, live_attempts):
            return CleanupReport(attempt_id, "retained", owner, _disk_bytes(path), "live")
        if record is None and attempt_id in live_attempts:
            return CleanupReport(attempt_id, "denied", owner, _disk_bytes(path), "unrecorded-live")
        measured = _disk_bytes(path)
        _remove_contained(path, root)
        _prune(root / "repo")
        _drop_record(root, attempt_id)
        report = CleanupReport(attempt_id, "removed", owner or "orphan", measured, "expired" if record else "orphan")
        _publish(store, report)
        return report

    def _git(self, argv: list[str], env: dict[str, str]) -> str:
        completed = subprocess.run(
            ["git", *argv],
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
        return completed.stdout


def _within_ttl(
    record: dict[str, object] | None,
    now: int,
    attempt_id: str,
    live_attempts: set[str],
) -> bool:
    if record is None or attempt_id not in live_attempts:
        return False
    created = record.get("created_at")
    ttl = record.get("ttl_seconds")
    if not isinstance(created, int) or not isinstance(ttl, int):
        return False
    return now < created + ttl


def _disk_bytes(worktree: Path) -> int:
    total = 0
    for dirpath, dirnames, filenames in os.walk(worktree, followlinks=False):
        current = Path(dirpath)
        dirnames[:] = [name for name in dirnames if not (current / name).is_symlink()]
        for name in filenames:
            child = current / name
            info = child.lstat()
            if stat.S_ISREG(info.st_mode):
                total += info.st_size
    return total


def _remove_contained(path: Path, root: Path) -> None:
    if not path.parent.resolve().is_relative_to(root):
        raise ValueError("cleanup escapes the sandbox")
    if path.is_symlink():
        path.unlink()
        return
    if path.is_dir():
        for child in list(path.iterdir()):
            _remove_contained(child, root)
        path.rmdir()
        return
    path.unlink()


def _record_path(root: Path, attempt_id: str) -> Path:
    return root / "protected" / "worktree-records" / f"{attempt_id}.json"


def _write_record(root: Path, manifest: WorkspaceManifest) -> None:
    body = {
        "attempt_id": manifest.attempt_id,
        "created_at": manifest.created_at,
        "disk_bytes": manifest.disk_bytes,
        "owner": manifest.owner,
        "ttl_seconds": manifest.ttl_seconds,
    }
    destination = _record_path(root, manifest.attempt_id)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _read_records(root: Path) -> dict[str, dict[str, object]]:
    directory = root / "protected" / "worktree-records"
    if not directory.is_dir() or directory.is_symlink():
        return {}
    found: dict[str, dict[str, object]] = {}
    for child in directory.iterdir():
        if child.suffix != ".json" or child.is_symlink():
            continue
        loaded = json.loads(child.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and isinstance(loaded.get("attempt_id"), str):
            found[str(loaded["attempt_id"])] = loaded
    return found


def _drop_record(root: Path, attempt_id: str) -> None:
    path = _record_path(root, attempt_id)
    if path.is_file() and not path.is_symlink():
        path.unlink()


def _publish(store: Path | None, report: CleanupReport) -> None:
    if store is None or report.outcome != "removed":
        return
    store.mkdir(parents=True, exist_ok=True)
    body = json.dumps(
        {
            "attempt_id": report.attempt_id,
            "disk_bytes": report.disk_bytes,
            "outcome": report.outcome,
            "owner": report.owner,
            "reason": report.reason,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    digest = hashlib.sha256(body).hexdigest()
    destination = store / digest
    if destination.is_symlink():
        raise ValueError("store symlink")
    if destination.exists():
        return
    temporary = store / f".{digest}.partial"
    temporary.write_bytes(body)
    temporary.replace(destination)


def _prune(repo: Path) -> None:
    if not repo.is_dir() or repo.is_symlink():
        return
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "prune"],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
