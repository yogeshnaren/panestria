"""Credential-free native version/help inside the existing offline OS envelope.

Only the fixed pinned binary, an empty read-only workspace and trusted launcher
are mounted. No auth/config reference, prompt, environment or argv is accepted.
This is bootstrap metadata, never task/native-auth conformance or runtime grant.
"""

from __future__ import annotations

import hashlib
import os
import platform
import re
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from panestria.brokers.harness.claude_proposal import PINNED_BINARY_SHA256
from panestria.brokers.harness.cli_profile import (
    MAX_BINARY,
    PROBE_PREFIX,
    VISIBLE_CONTROLS,
    BinaryPin,
    NativeProbeUnavailable,
    _unchanged,
)
from panestria.brokers.harness.event_parser import CLAUDE_VERSION
from panestria.sandbox.profiles import DEFAULT_IMAGE, ReadOnlyMount, SandboxProfile, SandboxRejected
from panestria.sandbox.runner import DockerSandbox, SandboxReceipt


class NativeBootstrapUnavailable(Exception):
    """Static codes only; no raw native/Docker output or filesystem details."""


@dataclass(frozen=True)
class BootstrapRun:
    mode: Literal["version", "help"]
    container_id: str
    profile_sha256: str
    effective_config_sha256: str
    output_sha256: str
    elapsed_seconds: float


@dataclass(frozen=True)
class NativeBootstrapObservation:
    binary_sha256: str
    version: str
    image: str
    controls: tuple[str, ...]
    runs: tuple[BootstrapRun, ...]
    status: Literal["BOOTSTRAP_ONLY"] = field(default="BOOTSTRAP_ONLY", init=False)
    authentication_observed: bool = field(default=False, init=False)
    inference_observed: bool = field(default=False, init=False)
    runtime_authority: bool = field(default=False, init=False)


def _snapshot(pin: BinaryPin, descriptor: int, destination: Path, deadline: float) -> None:
    """Copy a held verified executable to a private stable bind source, never auth."""
    _unchanged(pin, descriptor, deadline)
    os.lseek(descriptor, 0, os.SEEK_SET)
    digest, total = hashlib.sha256(), 0
    with destination.open("xb") as target:
        while chunk := os.read(descriptor, 1024**2):
            total += len(chunk)
            if total > MAX_BINARY or time.monotonic() >= deadline:
                raise NativeBootstrapUnavailable("native_bootstrap_snapshot_limit")
            digest.update(chunk)
            target.write(chunk)
    if digest.hexdigest() != pin.sha256:
        raise NativeBootstrapUnavailable("native_bootstrap_pin_changed")
    destination.chmod(0o500)
    _unchanged(pin, descriptor, deadline)


class NativeBootstrap:
    def inspect(
        self,
        pin: BinaryPin,
        *,
        wall_seconds: float = 10.0,
        cancel: threading.Event | None = None,
    ) -> NativeBootstrapObservation:
        if (
            not isinstance(pin, BinaryPin)
            or not isinstance(pin.path, Path)
            or not pin.path.is_absolute()
            or pin.path.resolve() != pin.path
            or pin.sha256 != PINNED_BINARY_SHA256
            or type(wall_seconds) not in {int, float}
            or not 0.1 <= wall_seconds <= 15
        ):
            raise NativeBootstrapUnavailable("invalid_native_bootstrap_reference")
        if platform.system() != "Linux" or platform.machine() != "x86_64" or os.geteuid() == 0:
            raise NativeBootstrapUnavailable("native_bootstrap_platform_unavailable")
        if cancel is not None and cancel.is_set():
            raise NativeBootstrapUnavailable("native_bootstrap_cancelled")
        descriptor = -1
        try:
            descriptor = os.open(pin.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with tempfile.TemporaryDirectory(prefix="panestria-native-bootstrap-", dir="/tmp") as directory:
                root = Path(directory)
                root.chmod(0o700)
                executable, workspace = root / "pinned-native", root / "empty-workspace"
                workspace.mkdir(mode=0o700)
                _snapshot(pin, descriptor, executable, time.monotonic() + 10)
                staged = BinaryPin(executable, pin.sha256)
                sandbox = DockerSandbox(root, runtime_mounts=(ReadOnlyMount(executable, "/runtime/native"),))
                profile = SandboxProfile(
                    name="restricted-offline",
                    uid=os.getuid(),
                    gid=os.getgid(),
                    memory_bytes=512 * 1024**2,
                    cpu_nanos=1_000_000_000,
                    pids=64,
                    wall_seconds=wall_seconds,
                )
                runs: list[BootstrapRun] = []
                controls: tuple[str, ...] = ()
                modes: tuple[Literal["version", "help"], ...] = ("version", "help")
                for mode in modes:
                    _unchanged(pin, descriptor, time.monotonic() + 5)
                    with executable.open("rb") as held:
                        _unchanged(staged, held.fileno(), time.monotonic() + 5)
                    result = sandbox.run(
                        workspace, ("/runtime/native", *PROBE_PREFIX, "--" + mode), profile, cancel=cancel
                    )
                    self._completed(result)
                    text = result.output.decode("utf-8", errors="strict")
                    if mode == "version" and text.strip() != CLAUDE_VERSION + " (Claude Code)":
                        raise NativeBootstrapUnavailable("native_bootstrap_version_mismatch")
                    if mode == "help":
                        advertised = set(re.findall(r"--[a-z][a-zA-Z-]*", text))
                        if not VISIBLE_CONTROLS <= advertised:
                            raise NativeBootstrapUnavailable("native_bootstrap_controls_missing")
                        controls = tuple(sorted(VISIBLE_CONTROLS))
                    runs.append(
                        BootstrapRun(
                            mode,
                            result.container_id,
                            result.profile_sha256,
                            result.effective_config_sha256,
                            hashlib.sha256(result.output).hexdigest(),
                            result.elapsed_seconds,
                        )
                    )
                    _unchanged(pin, descriptor, time.monotonic() + 5)
                    with executable.open("rb") as held:
                        _unchanged(staged, held.fileno(), time.monotonic() + 5)
                return NativeBootstrapObservation(pin.sha256, CLAUDE_VERSION, DEFAULT_IMAGE, controls, tuple(runs))
        except (OSError, ValueError, NativeProbeUnavailable, SandboxRejected):
            raise NativeBootstrapUnavailable("native_bootstrap_unavailable") from None
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    @staticmethod
    def _completed(result: SandboxReceipt) -> None:
        if result.reason != "completed" or result.exit_code != 0 or result.oom_killed:
            code = (
                result.reason
                if result.reason in {"cancelled", "deadline_exceeded", "output_limit", "memory_limit"}
                else "failed"
            )
            raise NativeBootstrapUnavailable("native_bootstrap_" + code)
