"""Scripted worker process. Completion stays a candidate until independent checks exist."""

from __future__ import annotations

import hashlib
import os
import selectors
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
    def __init__(
        self,
        manifest: WorkspaceManifest,
        mode: str,
        seed: str,
        output_limit: int = OUTPUT_LIMIT,
        relative: str = "allowed.txt",
    ) -> None:
        self.manifest = manifest
        self.mode = mode
        self.seed = seed
        self.output_limit = output_limit
        self.relative = relative
        self._process: subprocess.Popen[bytes] | None = None
        self._cancellation_requested = False
        self._terminated = False
        self._timed_out = False

    def start(self) -> None:
        env = os.environ.copy()
        env["PANESTRIA_WORKER_MODE"] = self.mode
        env["PANESTRIA_WORKER_SEED"] = self.seed
        env["PANESTRIA_WORKTREE"] = self.manifest.worktree
        env["PANESTRIA_SANDBOX_ROOT"] = self.manifest.root
        env["PANESTRIA_WORKER_RELATIVE"] = self.relative
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
        if process is None or process.stdout is None or process.stderr is None:
            raise RuntimeError("worker has not started")
        kept, truncated = self._capture(process, timeout)
        if process.poll() is not None:
            self._terminated = True
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

    def _capture(self, process: subprocess.Popen[bytes], timeout: float) -> tuple[bytes, bool]:
        assert process.stdout is not None and process.stderr is not None
        stdout_fd = process.stdout.fileno()
        stderr_fd = process.stderr.fileno()
        os.set_blocking(stdout_fd, False)
        os.set_blocking(stderr_fd, False)
        selector = selectors.DefaultSelector()
        selector.register(stdout_fd, selectors.EVENT_READ, "out")
        selector.register(stderr_fd, selectors.EVENT_READ, "err")
        kept = bytearray()
        truncated = False
        deadline = time.monotonic() + timeout
        try:
            while process.poll() is None and time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                for key, _mask in selector.select(remaining):
                    keep = kept if key.data == "out" else None
                    truncated = self._consume(key.fd, keep) or truncated
            if process.poll() is None and not self._cancellation_requested:
                self._timed_out = True
                self._kill()
            truncated = self._consume(stdout_fd, kept) or truncated
            self._consume(stderr_fd, None)
        finally:
            selector.close()
        return bytes(kept), truncated

    def _consume(self, fd: int, kept: bytearray | None) -> bool:
        truncated = False
        while True:
            try:
                chunk = os.read(fd, 65536)
            except BlockingIOError:
                return truncated
            if not chunk:
                return truncated
            if kept is None:
                continue
            room = self.output_limit - len(kept)
            if len(chunk) <= room:
                kept += chunk
                continue
            if room > 0:
                kept += chunk[:room]
            truncated = True

    def _kill(self) -> None:
        process = self._process
        if process is None or self._terminated:
            return
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
        self._terminated = True

    def _group_alive(self, pid: int) -> bool:
        try:
            os.killpg(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def _status(self, returncode: int | None) -> str:
        if self._cancellation_requested:
            return "CANCELLED"
        if self._timed_out:
            process = self._process
            if process is not None and self._group_alive(process.pid):
                return "UNKNOWN"
            return "TIMED_OUT"
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
        worktree = Path(self.manifest.worktree)
        allowed = {".git", "README.txt", self.relative}
        if self.relative == "allowed.txt":
            allowed.update(ALLOWLIST)
        for dirpath, dirnames, filenames in os.walk(worktree, followlinks=False):
            dirnames[:] = [name for name in dirnames if name != ".git"]
            for name in filenames:
                relative = (Path(dirpath) / name).relative_to(worktree).as_posix()
                if relative not in allowed:
                    return True
        return False

    def _artifact_hash(self) -> str:
        path = Path(self.manifest.worktree) / self.relative
        if not path.is_file():
            return ""
        return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative_file(worktree: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or relative == "":
        raise SystemExit(2)
    target = (worktree / path).resolve()
    if not target.is_relative_to(worktree.resolve()):
        raise SystemExit(2)
    return target


def main() -> None:
    mode = os.environ["PANESTRIA_WORKER_MODE"]
    seed = os.environ["PANESTRIA_WORKER_SEED"]
    worktree = Path(os.environ["PANESTRIA_WORKTREE"])
    root = Path(os.environ["PANESTRIA_SANDBOX_ROOT"])
    if mode in {"success", "verbose"}:
        relative = os.environ.get("PANESTRIA_WORKER_RELATIVE", "allowed.txt")
        target = _relative_file(worktree, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"edit:{seed}\n")
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
    if mode == "false_done":
        sys.stdout.write("done\n")
        sys.stdout.flush()
        while True:
            time.sleep(0.2)
    if mode == "flood":
        while True:
            sys.stdout.buffer.write(b"x" * 1024)
            sys.stdout.buffer.flush()
    if mode == "crash":
        os.kill(os.getpid(), signal.SIGKILL)
    raise SystemExit(2)


if __name__ == "__main__":
    main()
