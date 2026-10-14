"""Reviewed command dispatch behind an OS boundary; no model-issued authority."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, Protocol

from panestria.contracts.native_tools import ToolRequest, ToolScope
from panestria.sandbox.profiles import ReadOnlyMount, SandboxProfile, SandboxRejected
from panestria.sandbox.runner import DockerSandbox, SandboxReceipt


class GatewayRejected(Exception):
    """Static, content-free refusal before dispatch claim."""


@dataclass(frozen=True)
class ReviewedCommand:
    ref: str
    script: Path
    sha256: str
    access: Literal["read", "edit"]


@dataclass(frozen=True)
class NativeCommandRegistry:
    """Constructed by the trusted controller; worker registration is not exposed."""

    commands: tuple[ReviewedCommand, ...]

    def sha256(self) -> str:
        rows = [{"ref": cmd.ref, "sha256": cmd.sha256, "access": cmd.access} for cmd in self.commands]
        return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def resolve(self, ref: str) -> ReviewedCommand:
        if (
            not self.commands
            or len(self.commands) > 64
            or len({cmd.ref for cmd in self.commands}) != len(self.commands)
            or any(
                re.fullmatch(r"[a-z][a-z0-9-]{0,63}", cmd.ref) is None
                or re.fullmatch(r"[0-9a-f]{64}", cmd.sha256) is None
                or cmd.access not in {"read", "edit"}
                for cmd in self.commands
            )
        ):
            raise GatewayRejected("invalid_registry")
        for command in self.commands:
            if command.ref == ref:
                return command
        raise GatewayRejected("unregistered_command")


@dataclass(frozen=True)
class ToolPermit:
    """Controller-only binding. Never accept this object from a worker/API body."""

    scope: ToolScope
    request_sha256: str
    registry_sha256: str
    workspace: Path
    profile: SandboxProfile
    deadline_monotonic: float


class ToolAuthority(Protocol):
    """Controller boundary, not a boolean supplied by a model.

    claim must commit a unique dispatch intent before returning, checking actor,
    project, task, attempt/epoch, contract, policy, request/registry and workspace.
    Replays must fail, including after an unknown outcome. check must recheck
    current lease/policy/cancellation. Both calls must have bounded I/O timeouts.
    The gateway does not implement another task store or grant permissions.
    """

    def claim(self, permit: ToolPermit) -> None: ...
    def check(self, permit: ToolPermit) -> None: ...


ToolOutcome = Literal["completed", "failed", "cancelled", "deadline_exceeded", "authority_revoked", "unknown"]


@dataclass(frozen=True)
class ToolReceipt:
    request_sha256: str
    scope_sha256: str
    registry_sha256: str
    outcome: ToolOutcome
    sandbox: SandboxReceipt | None
    # A tool result is never independent verification or kernel completion.


RunnerFactory = Callable[[Path, tuple[ReadOnlyMount, ...]], DockerSandbox]


def _runner(root: Path, mounts: tuple[ReadOnlyMount, ...]) -> DockerSandbox:
    return DockerSandbox(root, runtime_mounts=mounts)


def _script_bytes(command: ReviewedCommand, workspace_root: Path) -> bytes:
    path = command.script
    try:
        safe_path = path.is_absolute() and path.resolve() == path and not path.is_relative_to(workspace_root)
    except (OSError, RuntimeError):
        safe_path = False
    if not safe_path:
        raise GatewayRejected("unreviewed_script_path")
    fd = -1
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid not in {0, os.getuid()}
            or info.st_mode & 0o022
            or not 1 <= info.st_size <= 256 * 1024
        ):
            raise GatewayRejected("unsafe_command_script")
        with os.fdopen(fd, "rb", closefd=False) as source:
            data = source.read(256 * 1024 + 1)
        if len(data) > 256 * 1024 or hashlib.sha256(data).hexdigest() != command.sha256:
            raise GatewayRejected("command_digest_mismatch")
        return data
    except OSError:
        raise GatewayRejected("command_unavailable") from None
    finally:
        if fd >= 0:
            os.close(fd)


class NativeToolGateway:
    def __init__(
        self,
        workspace_root: Path,
        registry: NativeCommandRegistry,
        authority: ToolAuthority,
        *,
        runner_factory: RunnerFactory = _runner,
    ) -> None:
        self.root = workspace_root.resolve()
        self.registry = registry
        self.authority = authority
        self._runner = runner_factory

    def execute(
        self, request: ToolRequest, permit: ToolPermit, *, cancel: threading.Event | None = None
    ) -> ToolReceipt:
        try:
            request_hash = request.sha256()
        except ValueError:
            raise GatewayRejected("tool_request_limit") from None
        registry_hash = self.registry.sha256()
        if request_hash != permit.request_sha256 or registry_hash != permit.registry_sha256:
            raise GatewayRejected("permit_binding_mismatch")
        command = self.registry.resolve(request.command_ref)
        workspace = permit.workspace
        try:
            valid_workspace = (
                workspace.is_absolute()
                and workspace.resolve() == workspace
                and workspace.is_dir()
                and workspace != self.root
                and workspace.is_relative_to(self.root)
            )
        except (OSError, RuntimeError):
            valid_workspace = False
        if not valid_workspace:
            raise GatewayRejected("workspace_scope_denied")
        try:
            permit.profile.validate()
        except SandboxRejected:
            raise GatewayRejected("invalid_tool_profile") from None
        if (command.access == "read" and permit.profile.name not in {"read-only-research", "restricted-offline"}) or (
            command.access == "edit" and permit.profile.name != "scoped-code-edit"
        ):
            raise GatewayRejected("command_access_mismatch")
        remaining = permit.deadline_monotonic - time.monotonic()
        if not math.isfinite(remaining) or not 0.1 <= remaining <= 900:
            raise GatewayRejected("invalid_tool_deadline")
        if cancel is not None and cancel.is_set():
            raise GatewayRejected("cancelled_before_claim")
        script_bytes = _script_bytes(command, self.root)
        envelope = request.canonical_bytes()
        # Snapshot only the reviewed script and data, never a whole host bundle.
        # The host directory is private; each individually mounted file is
        # readable by the configured nonroot container UID and mounted readonly.
        # Ignore inherited TMPDIR: it could point into an editable candidate.
        with tempfile.TemporaryDirectory(prefix="panestria-native-call-", dir="/tmp") as directory:
            stage = Path(directory)
            script = stage / "command.py"
            payload = stage / "request.json"
            script.write_bytes(script_bytes)
            payload.write_bytes(envelope)
            script.chmod(0o444)
            payload.chmod(0o444)
            mounts = (
                ReadOnlyMount(script, "/runtime/native-command.py"),
                ReadOnlyMount(payload, "/runtime/native-request.json"),
                ReadOnlyMount(Path(__file__).with_name("native_tool_launch.py"), "/runtime/native-launch.py"),
            )
            runner = self._runner(self.root, mounts)
            try:
                self.authority.claim(permit)
            except Exception:
                raise GatewayRejected("dispatch_claim_denied") from None
            return self._dispatch(request_hash, registry_hash, permit, command, runner, cancel)

    def _dispatch(
        self,
        request_hash: str,
        registry_hash: str,
        permit: ToolPermit,
        command: ReviewedCommand,
        runner: DockerSandbox,
        cancel: threading.Event | None,
    ) -> ToolReceipt:
        stop = threading.Event()
        done = threading.Event()
        revoked = threading.Event()
        expired = threading.Event()
        unavailable = threading.Event()

        def check() -> None:
            if cancel is not None and cancel.is_set():
                stop.set()
            if time.monotonic() >= permit.deadline_monotonic:
                expired.set()
                stop.set()
            if unavailable.is_set():
                return
            checked = threading.Event()

            def inspect_authority() -> None:
                try:
                    self.authority.check(permit)
                except Exception:
                    revoked.set()
                    stop.set()
                finally:
                    checked.set()

            # A stalled read-only controller check cannot hang worker shutdown
            # or authorize a result. Controller I/O still needs its own timeout
            # to release the daemon check thread and its database connection.
            probe = threading.Thread(target=inspect_authority, daemon=True, name="panestria-tool-check")
            probe.start()
            if not checked.wait(timeout=0.5):
                unavailable.set()
                stop.set()

        def monitor() -> None:
            while not done.wait(0.1):
                check()

        sandbox: SandboxReceipt | None = None
        dispatched = False
        watchdog = threading.Thread(target=monitor, daemon=True, name="panestria-tool-authority")
        check()
        watchdog.start()
        try:
            remaining = permit.deadline_monotonic - time.monotonic()
            if not stop.is_set() and remaining >= 0.1:
                profile = replace(permit.profile, wall_seconds=min(permit.profile.wall_seconds, remaining))
                try:
                    dispatched = True
                    sandbox = runner.run(
                        permit.workspace,
                        (
                            "/usr/local/bin/python",
                            "-I",
                            "/runtime/native-launch.py",
                            command.sha256,
                            request_hash,
                        ),
                        profile,
                        # The invocation has its own identity; the attempt can
                        # contain multiple separately claimed tool calls.
                        cancel=stop,
                    )
                except Exception:
                    # Claim is already committed. An exception cannot prove no
                    # effect or safe retry, even if container cleanup failed.
                    sandbox = None
        finally:
            done.set()
            watchdog.join(timeout=1)
        if not watchdog.is_alive():
            check()
        outcome: ToolOutcome
        if watchdog.is_alive() or unavailable.is_set() or (dispatched and sandbox is None):
            outcome = "unknown"
        elif revoked.is_set():
            outcome = "authority_revoked"
        elif expired.is_set():
            outcome = "deadline_exceeded"
        elif cancel is not None and cancel.is_set():
            outcome = "cancelled"
        elif sandbox is None:
            outcome = "unknown"
        elif sandbox.reason == "completed" and sandbox.exit_code == 0:
            outcome = "completed"
        elif sandbox.reason == "deadline_exceeded":
            outcome = "deadline_exceeded"
        else:
            outcome = "failed"
        return ToolReceipt(request_hash, permit.scope.sha256(), registry_hash, outcome, sandbox)
