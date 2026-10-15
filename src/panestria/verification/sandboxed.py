"""Candidate code is verified in a separate readonly, secret-free OS boundary."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from panestria.sandbox.profiles import ReadOnlyMount, SandboxProfile, SandboxRejected
from panestria.sandbox.runner import DockerSandbox
from panestria.telemetry.tracing import metadata_span
from panestria.verification.registry import CommandRegistry
from panestria.verification.runner import CheckResult


class SandboxedCheckRunner:
    def __init__(self, registry: CommandRegistry, candidate_root: Path) -> None:
        self.registry, self.root = registry, candidate_root.resolve()

    def run(self, ref: str, candidate: Path, deadline_seconds: float, *, expected_exit_code: int = 0) -> CheckResult:
        try:
            command = self.registry.resolve(ref)
        except KeyError:
            return CheckResult(ref, "FAIL", "unregistered_command")
        if deadline_seconds <= 0 or deadline_seconds > 300:
            return CheckResult(ref, "FAIL", "deadline")
        if len(command.argv) != 2 or command.argv[0] != self.registry.interpreter:
            return CheckResult(ref, "FAIL", "unreviewed_executable_or_args")
        script = Path(command.argv[1])
        if script.is_symlink() or script.resolve().parent != self.registry.bundle_root:
            return CheckResult(ref, "FAIL", "unreviewed_path")
        if hashlib.sha256(script.read_bytes()).hexdigest() != command.script_sha256:
            return CheckResult(ref, "FAIL", "bundle_tampered")
        runner = DockerSandbox(
            self.root,
            runtime_mounts=(
                ReadOnlyMount(self.registry.bundle_root, "/runtime/checks"),
                ReadOnlyMount(Path(__file__).with_name("sandbox_launch.py"), "/runtime/verify-launch.py"),
            ),
        )
        profile = SandboxProfile(
            name="restricted-offline",
            uid=os.getuid(),
            gid=os.getgid(),
            memory_bytes=256 * 1024 * 1024,
            cpu_nanos=1_000_000_000,
            pids=64,
            wall_seconds=deadline_seconds,
            output_bytes=4096,
        )
        try:
            with metadata_span("verifier.run", **{"panestria.privacy_label": "RESTRICTED"}):
                receipt = runner.run(
                    candidate,
                    (
                        "/usr/local/bin/python",
                        "-I",
                        "/runtime/verify-launch.py",
                        f"/runtime/checks/{script.name}",
                        command.script_sha256,
                    ),
                    profile,
                )
        except SandboxRejected as exc:
            return CheckResult(ref, "FAIL", str(exc))
        passed = receipt.reason == "completed" and receipt.exit_code == expected_exit_code
        return CheckResult(
            ref,
            "PASS" if passed else "FAIL",
            "ok" if passed else receipt.reason,
            receipt.exit_code,
            hashlib.sha256(receipt.output).hexdigest(),
            receipt.reason == "output_limit",
            receipt.output,
        )
