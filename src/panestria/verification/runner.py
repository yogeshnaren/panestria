"""Run one reviewed argv. The bundle hash is checked again before the process starts."""

from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from panestria.verification.registry import CommandRegistry


@dataclass(frozen=True)
class CheckResult:
    ref: str
    verdict: str
    reason: str


class TrustedCheckRunner:
    def __init__(self, registry: CommandRegistry) -> None:
        self.registry = registry

    def run(self, ref: str, candidate: Path, deadline_seconds: float) -> CheckResult:
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
        try:
            completed = subprocess.run(
                list(command.argv),
                cwd=self.registry.bundle_root,
                env=env,
                capture_output=True,
                timeout=deadline_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return CheckResult(ref, "FAIL", "timeout")
        if completed.returncode == 0:
            return CheckResult(ref, "PASS", "ok")
        return CheckResult(ref, "FAIL", f"exit_{completed.returncode}")
