"""Run one reviewed argv. Output and time are bounded before a verdict is kept."""

from __future__ import annotations

import hashlib
import os
import selectors
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from panestria.verification.registry import CommandRegistry

OUTPUT_LIMIT = 4096


@dataclass(frozen=True)
class CheckResult:
    ref: str
    verdict: str
    reason: str
    exit_code: int | None = None
    output_sha256: str = ""
    truncated: bool = False
    output: bytes = b""


class TrustedCheckRunner:
    def __init__(self, registry: CommandRegistry) -> None:
        self.registry = registry

    def run(
        self,
        ref: str,
        candidate: Path,
        deadline_seconds: float,
        *,
        expected_exit_code: int = 0,
    ) -> CheckResult:
        command = self.registry.resolve(ref)
        if deadline_seconds <= 0:
            return CheckResult(ref, "FAIL", "deadline")
        if command.argv[0] != self.registry.interpreter:
            return CheckResult(ref, "FAIL", "unreviewed_executable")
        script = Path(command.argv[-1]).resolve()
        if script.parent != self.registry.bundle_root:
            return CheckResult(ref, "FAIL", "unreviewed_path")
        if candidate.is_symlink():
            return CheckResult(ref, "FAIL", "symlink")
        current = hashlib.sha256(script.read_bytes()).hexdigest()
        if current != command.script_sha256:
            return CheckResult(ref, "FAIL", "bundle_tampered")
        env = {
            "PATH": os.environ.get("PATH", ""),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PANESTRIA_CANDIDATE": str(candidate.resolve()),
        }
        exit_code, output, failure = _bounded(list(command.argv), self.registry.bundle_root, env, deadline_seconds)
        digest = hashlib.sha256(output).hexdigest()
        if failure == "timeout":
            return CheckResult(ref, "FAIL", "timeout", exit_code, digest, False, output)
        if failure == "output_limit":
            return CheckResult(ref, "FAIL", "output_limit", exit_code, digest, True, output)
        if exit_code == expected_exit_code:
            return CheckResult(ref, "PASS", "ok", exit_code, digest, False, output)
        return CheckResult(ref, "FAIL", f"exit_{exit_code}", exit_code, digest, False, output)


def _bounded(
    argv: list[str],
    cwd: Path,
    env: dict[str, str],
    deadline_seconds: float,
) -> tuple[int | None, bytes, str]:
    process = subprocess.Popen(
        argv,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    assert process.stdout is not None and process.stderr is not None
    stdout_fd = process.stdout.fileno()
    stderr_fd = process.stderr.fileno()
    os.set_blocking(stdout_fd, False)
    os.set_blocking(stderr_fd, False)
    selector = selectors.DefaultSelector()
    selector.register(stdout_fd, selectors.EVENT_READ)
    selector.register(stderr_fd, selectors.EVENT_READ)
    kept = bytearray()
    failure = ""
    deadline = time.monotonic() + deadline_seconds
    try:
        while process.poll() is None and failure == "":
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failure = "timeout"
                break
            events = selector.select(remaining)
            if not events and process.poll() is None and time.monotonic() >= deadline:
                failure = "timeout"
                break
            for key, _mask in events:
                if _take(key.fd, kept):
                    failure = "output_limit"
                    break
        if failure == "":
            if _take(stdout_fd, kept) or _take(stderr_fd, kept):
                failure = "output_limit"
    finally:
        selector.close()
        if failure != "":
            _kill(process)
        else:
            process.wait(timeout=5)
    return process.returncode, bytes(kept), failure


def _take(fd: int, kept: bytearray) -> bool:
    overflow = False
    while True:
        try:
            chunk = os.read(fd, 65536)
        except BlockingIOError:
            return overflow
        if not chunk:
            return overflow
        room = OUTPUT_LIMIT - len(kept)
        if len(chunk) <= room:
            kept += chunk
            continue
        if room > 0:
            kept += chunk[:room]
        overflow = True
        return overflow


def _kill(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=5)
