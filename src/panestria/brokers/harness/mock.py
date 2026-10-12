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
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from panestria.sandbox.worktree import WorkspaceManifest

OUTPUT_LIMIT = 4096
ALLOWLIST = frozenset({"allowed.txt"})
_EVENT_NAMES = ("started", "progress", "artifact.created", "verifying", "finished")
_MODES = frozenset(
    {
        "artifact_corrupt",
        "bad_path",
        "bad_test",
        "crash",
        "false_done",
        "false_readme",
        "flood",
        "hung",
        "success",
        "timeout",
        "verbose",
    }
)


@dataclass(frozen=True)
class Observation:
    cancellation_requested: bool
    terminated: bool
    running: bool


@dataclass(frozen=True)
class WorkerEvent:
    name: str
    event_id: str
    attempt_id: str
    epoch: int


class WorkerAdapter(Protocol):
    def capabilities(self) -> frozenset[str]:
        """Modes this adapter can run. A name outside this set is not a command."""

    def validate(self) -> None:
        """Reject an unknown mode, seed, path, or epoch before a process starts."""

    def start(self) -> None:
        """Start the scripted process after validation."""

    def events(self) -> tuple[WorkerEvent, ...]:
        """Lifecycle events recorded so far. They do not accept the candidate."""

    def observe(self) -> Observation:
        """Report cancellation, termination, and whether the process is still running."""

    def cancel(self) -> None:
        """Record cancellation, then terminate the process group."""

    def collect(self, timeout: float = 5) -> Candidate:
        """Drain bounded output and return a candidate that stays unaccepted."""


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
        *,
        epoch: int = 1,
    ) -> None:
        self.manifest = manifest
        self.mode = mode.replace("-", "_")
        self.seed = seed
        self.output_limit = output_limit
        self.relative = relative
        self.epoch = epoch
        self._process: subprocess.Popen[bytes] | None = None
        self._cancellation_requested = False
        self._terminated = False
        self._timed_out = False
        self._events: list[WorkerEvent] = []

    def capabilities(self) -> frozenset[str]:
        return _MODES

    def validate(self) -> None:
        if self.mode not in _MODES:
            raise ValueError("worker mode")
        if not isinstance(self.seed, str) or self.seed == "" or len(self.seed) > 128 or "\n" in self.seed:
            raise ValueError("worker seed")
        if not isinstance(self.epoch, int) or isinstance(self.epoch, bool) or self.epoch < 0:
            raise ValueError("worker epoch")
        path = Path(self.relative)
        if path.is_absolute() or self.relative == "" or ".." in path.parts:
            raise ValueError("worker path")

    def events(self) -> tuple[WorkerEvent, ...]:
        return tuple(self._events)

    def start(self) -> None:
        self.validate()
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
        self._record("started")

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
        artifact = self._claimed_artifact(kept) if self.mode == "artifact_corrupt" else self._artifact_hash()
        status = self._status(process.returncode)
        if self._escaped():
            status = "REJECTED"
        for name in _EVENT_NAMES[1:]:
            self._record(name)
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

    def _record(self, name: str) -> None:
        if any(event.name == name for event in self._events):
            return
        token = f"{self.manifest.attempt_id}:{self.seed}:{self.epoch}:{name}"
        self._events.append(
            WorkerEvent(
                name=name,
                event_id=str(uuid5(NAMESPACE_URL, token)),
                attempt_id=self.manifest.attempt_id,
                epoch=self.epoch,
            )
        )

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
        if self.mode in {"bad_test", "artifact_corrupt"} and returncode == 0 and not self._escaped():
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

    def _claimed_artifact(self, kept: bytes) -> str:
        claimed = kept.decode(errors="replace").strip()
        if len(claimed) == 64 and all(character in "0123456789abcdef" for character in claimed):
            return claimed
        return ""


def _relative_file(worktree: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or relative == "":
        raise SystemExit(2)
    target = (worktree / path).resolve()
    if not target.is_relative_to(worktree.resolve()):
        raise SystemExit(2)
    return target


def main() -> None:
    mode = os.environ["PANESTRIA_WORKER_MODE"].replace("-", "_")
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
    if mode == "artifact_corrupt":
        relative = os.environ.get("PANESTRIA_WORKER_RELATIVE", "allowed.txt")
        target = _relative_file(worktree, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        original = f"edit:{seed}\n".encode()
        target.write_bytes(original)
        sys.stdout.write(hashlib.sha256(original).hexdigest() + "\n")
        target.write_bytes(b"mutated\n")
        return
    if mode == "bad_test":
        relative = os.environ.get("PANESTRIA_WORKER_RELATIVE", "allowed.txt")
        target = _relative_file(worktree, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("tests pass\n")
        sys.stdout.write("tests pass\n")
        return
    if mode == "bad_path":
        (root / "outside.txt").write_text("escape\n")
        sys.stdout.write("done\n")
        return
    if mode in {"hung", "timeout"}:
        while True:
            time.sleep(0.2)
    if mode == "false_readme":
        (worktree / "README.md").write_text("tests pass\n")
        sys.stdout.write("tests pass\n")
        return
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
