"""Scripted worker process. Completion stays a candidate until independent checks exist."""

from __future__ import annotations

import hashlib
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from panestria.sandbox.worktree import WorkspaceManifest

OUTPUT_LIMIT = 4096
ALLOWLIST = frozenset({"allowed.txt"})


@dataclass(frozen=True)
class Observation:
    cancellation_requested: bool
    terminated: bool
    running: bool


@dataclass(frozen=True)
class Candidate:
    status: str
    accepted: bool
    checks: str
    artifact_sha256: str
    stdout_sha256: str
    base_sha: str
    truncated: bool


class MockWorkerAdapter:
    def __init__(self, manifest: WorkspaceManifest, mode: str, seed: str, output_limit: int = OUTPUT_LIMIT) -> None:
        self.manifest = manifest
        self.mode = mode
        self.seed = seed
        self.output_limit = output_limit
        self._process: subprocess.Popen[bytes] | None = None
        self._cancellation_requested = False
        self._terminated = False

    def start(self) -> None:
        env = os.environ.copy()
        env["PANESTRIA_WORKER_MODE"] = self.mode
        env["PANESTRIA_WORKER_SEED"] = self.seed
        env["PANESTRIA_WORKTREE"] = self.manifest.worktree
        env["PANESTRIA_SANDBOX_ROOT"] = self.manifest.root
        self._process = subprocess.Popen(
            [sys.executable, "-m", "panestria.brokers.harness.mock"],
            cwd=self.manifest.worktree,
            env=env,
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def observe(self) -> Observation:
        running = self._process is not None and self._process.poll() is None and not self._terminated
        return Observation(self._cancellation_requested, self._terminated, running)

    def cancel(self) -> None:
        """Record the request, then the termination. The two states stay distinct."""
        self._cancellation_requested = True
        self._kill()

    def collect(self, timeout: float = 5) -> Candidate:
        process = self._process
        if process is None:
            raise RuntimeError("worker has not started")
        try:
            stdout, _stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.cancel()
            stdout, _stderr = process.communicate(timeout=2)
        else:
            self._terminated = True
        truncated = len(stdout) > self.output_limit
        kept = stdout[: self.output_limit]
        artifact = self._artifact_hash()
        status = self._status(process.returncode)
        if self._escaped():
            status = "REJECTED"
        return Candidate(
            status=status,
            accepted=False,
            checks="NOT_RUN",
            artifact_sha256=artifact,
            stdout_sha256=hashlib.sha256(kept).hexdigest(),
            base_sha=self.manifest.base_sha,
            truncated=truncated,
        )

    def _kill(self) -> None:
        process = self._process
        if process is None or self._terminated:
            return
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
        self._terminated = True

    def _status(self, returncode: int | None) -> str:
        if self._cancellation_requested:
            return "CANCELLED"
        if returncode is None or returncode < 0:
            return "CRASHED"
        if self.mode == "success" and returncode == 0 and not self._escaped():
            return "CANDIDATE"
        if self.mode == "verbose" and returncode == 0:
            return "CANDIDATE"
        return "REJECTED"

    def _escaped(self) -> bool:
        outside = Path(self.manifest.root) / "outside.txt"
        if outside.exists():
            return True
        for path in Path(self.manifest.worktree).iterdir():
            if path.name in {".git", "README.txt"} or path.name in ALLOWLIST:
                continue
            return True
        return False

    def _artifact_hash(self) -> str:
        path = Path(self.manifest.worktree) / "allowed.txt"
        if not path.is_file():
            return ""
        return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    mode = os.environ["PANESTRIA_WORKER_MODE"]
    seed = os.environ["PANESTRIA_WORKER_SEED"]
    worktree = Path(os.environ["PANESTRIA_WORKTREE"])
    root = Path(os.environ["PANESTRIA_SANDBOX_ROOT"])
    if mode in {"success", "verbose"}:
        (worktree / "allowed.txt").write_text(f"edit:{seed}\n")
        if mode == "verbose":
            sys.stdout.buffer.write(b"x" * 20000)
        else:
            sys.stdout.write("done\n")
        return
    if mode == "bad_path":
        (root / "outside.txt").write_text("escape\n")
        sys.stdout.write("done\n")
        return
    if mode == "hung":
        while True:
            time.sleep(0.2)
    if mode == "crash":
        os.kill(os.getpid(), signal.SIGKILL)
    raise SystemExit(2)


if __name__ == "__main__":
    main()
