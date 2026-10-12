"""Create a toy repository and one attempt worktree inside a caller-owned root."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

_ATTEMPT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
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


class WorktreeManager:
    def create(self, root: Path, attempt_id: str, seed: str) -> WorkspaceManifest:
        """Build the fixture under root. A user-supplied absolute path is not a root."""
        if not _ATTEMPT_ID.fullmatch(attempt_id):
            raise ValueError("attempt id is not a sandbox name")
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
        return WorkspaceManifest(str(base), str(repo), str(worktree), sha, attempt_id)

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
