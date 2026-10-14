"""Drain both pipes and enforce a wall deadline even when a native CLI is silent.

The caller supplies an already-approved isolated launch, never model-generated
argv. This supervisor is lifecycle control, not an OS security boundary.
"""

from __future__ import annotations

import hashlib
import os
import selectors
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from panestria.brokers.harness.event_parser import ClaudeEventParser, NativeResult, ProtocolRejected


@dataclass(frozen=True)
class ProcessReceipt:
    status: str
    terminated: bool
    exit_code: int | None
    reason: str
    stdout_sha256: str
    stderr_sha256: str
    result: NativeResult | None


def _terminate(process: subprocess.Popen[bytes]) -> bool:
    # The leader can exit while a child retains a pipe. Terminate the session's
    # process group as well, rather than equating leader exit with cleanup.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=0.5)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=2)
    return process.poll() is not None


def collect_native(
    argv: tuple[str, ...],
    cwd: Path,
    env: dict[str, str],
    parser: ClaudeEventParser,
    *,
    wall_seconds: float,
    cancel: threading.Event | None = None,
    output_bytes: int = 1024 * 1024,
) -> ProcessReceipt:
    if not argv or not 0 < wall_seconds <= 900 or not 1024 <= output_bytes <= 1024 * 1024:
        raise ValueError("invalid_process_limits")
    if cancel is not None and cancel.is_set():
        empty = hashlib.sha256(b"").hexdigest()
        return ProcessReceipt("CANCELLED", True, None, "cancelled_before_start", empty, empty, None)
    process = subprocess.Popen(
        argv,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    assert process.stdout is not None and process.stderr is not None
    streams = {"stdout": process.stdout, "stderr": process.stderr}
    hashes = {name: hashlib.sha256() for name in streams}
    total = 0
    reason = ""
    terminated = False
    deadline = time.monotonic() + wall_seconds
    with selectors.DefaultSelector() as selector:
        for name, stream in streams.items():
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, name)
        try:
            while selector.get_map():
                if cancel is not None and cancel.is_set():
                    reason = "cancelled"
                    break
                if time.monotonic() >= deadline:
                    reason = "timeout"
                    break
                for key, _ in selector.select(min(0.05, max(0, deadline - time.monotonic()))):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    total += len(chunk)
                    if total > output_bytes:
                        reason = "output_limit"
                        break
                    hashes[key.data].update(chunk)
                    if key.data == "stdout":
                        parser.feed(chunk)
                if reason:
                    break
            # EOF on both pipes does not imply process exit. Keep cancellation
            # responsive instead of blocking wait() for the remaining wall time.
            while not reason and process.poll() is None:
                if cancel is not None and cancel.is_set():
                    reason = "cancelled"
                elif time.monotonic() >= deadline:
                    reason = "timeout"
                else:
                    time.sleep(min(0.01, max(0, deadline - time.monotonic())))
            if reason:
                terminated = _terminate(process)
                return ProcessReceipt(
                    "CANCELLED" if reason == "cancelled" else "FAILED",
                    terminated,
                    process.returncode,
                    reason,
                    hashes["stdout"].hexdigest(),
                    hashes["stderr"].hexdigest(),
                    None,
                )
            result = parser.finish(process.returncode if process.returncode is not None else -1)
            terminated = _terminate(process)
            return ProcessReceipt(
                result.status,
                terminated,
                process.returncode,
                result.reason,
                hashes["stdout"].hexdigest(),
                hashes["stderr"].hexdigest(),
                result,
            )
        except ProtocolRejected as exc:
            terminated = _terminate(process)
            return ProcessReceipt(
                "REJECTED",
                terminated,
                process.returncode,
                str(exc),
                hashes["stdout"].hexdigest(),
                hashes["stderr"].hexdigest(),
                None,
            )
        finally:
            if not terminated:
                _terminate(process)
            for stream in streams.values():
                stream.close()
