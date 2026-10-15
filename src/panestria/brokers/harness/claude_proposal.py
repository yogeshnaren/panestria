"""Pinned Claude generates fixed synthetic candidate data with all native tools disabled.

The trusted native authentication process owns its login. Candidate code is
never executed by it; applying and verifying proposals use separate containers.
This profile does not certify native file, shell, MCP or arbitrary repository work.
"""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from panestria.brokers.harness.cli_profile import BinaryPin, CliProfileProbe, NativeProbeUnavailable, _unchanged
from panestria.brokers.harness.event_parser import ClaudeEventParser, ProtocolRejected, _invalid_constant, _pairs
from panestria.brokers.harness.process_runner import ProcessReceipt, collect_native
from panestria.contracts.native_proposal import PROFILE, PROMPT, PROMPT_SHA256, CodeProposal

PINNED_BINARY_SHA256 = "6c752e2cc7c110c9df15f26d8d134d438c5ae95dbd610efc1a308bf7f9c5f6c1"
MANAGED_PATHS = (
    Path("/etc/claude-code/managed-settings.json"),
    Path("/etc/claude-code/managed-settings.d"),
    Path("/etc/claude-code/managed-mcp.json"),
)


class ProposalUnavailable(Exception):
    pass


@dataclass(frozen=True)
class ProposalReceipt:
    status: str
    reason: str
    proposal: CodeProposal | None
    process: ProcessReceipt
    profile: str = PROFILE
    prompt_sha256: str = PROMPT_SHA256


class ClaudeProposalAdapter:
    def __init__(self, pin: BinaryPin, config_directory: Path, archive: Path) -> None:
        self.pin, self.config, self.archive = pin, config_directory, archive

    def inspect(self) -> None:
        if self.pin.sha256 != PINNED_BINARY_SHA256:
            raise ProposalUnavailable("unsupported_native_pin")
        if any(path.exists() or path.is_symlink() for path in MANAGED_PATHS):
            raise ProposalUnavailable("managed_configuration_present")
        # Do not read credentials. The official CLI reports redacted login state.
        manifest = CliProfileProbe(self.archive).inspect(self.pin, self.config)
        if manifest.status != "INSPECTED":
            raise ProposalUnavailable("native_login_unavailable")
        for name in ("managed-settings.json", "managed-settings.d", "managed-mcp.json"):
            if (self.config / name).exists() or (self.config / name).is_symlink():
                raise ProposalUnavailable("managed_configuration_present")

    def propose(self, *, wall_seconds: float = 90, cancel: threading.Event | None = None) -> ProposalReceipt:
        if not 1 <= wall_seconds <= 120:
            raise ProposalUnavailable("invalid_native_deadline")
        self.inspect()
        deadline = time.monotonic() + wall_seconds
        binary_fd = config_fd = -1
        try:
            binary_fd = os.open(self.pin.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            config_fd = os.open(self.config, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY)
            _unchanged(self.pin, binary_fd, deadline)
            held = os.fstat(config_fd)
            if (
                self.config.resolve() != self.config
                or held.st_uid != os.getuid()
                or stat.S_IMODE(held.st_mode) != 0o700
            ):
                raise ProposalUnavailable("private_native_profile_required")
            with tempfile.TemporaryDirectory(prefix="panestria-proposal-", dir="/tmp") as folder:
                root = Path(folder)
                prompt = root / "task.txt"
                prompt.write_text(PROMPT)
                prompt.chmod(0o400)
                env = {
                    "PATH": "/usr/bin:/bin",
                    "HOME": folder,
                    "LANG": "C.UTF-8",
                    "CLAUDE_CONFIG_DIR": f"/proc/self/fd/{config_fd}",
                    "DISABLE_AUTOUPDATER": "1",
                    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                    "DISABLE_TELEMETRY": "1",
                    "DISABLE_ERROR_REPORTING": "1",
                }
                argv = (
                    f"/proc/self/fd/{binary_fd}",
                    "--safe-mode",
                    "--restricted",
                    "--print",
                    "--output-format",
                    "stream-json",
                    "--verbose",
                    "--tools",
                    "",
                    "--permission-prompts",
                    "none",
                    "--permission-mode",
                    "default",
                    "--no-session-persistence",
                    "--max-turns",
                    "2",
                    "--max-budget-usd",
                    "0.25",
                    "--model",
                    "haiku",
                    "--system-prompt-file",
                    str(prompt),
                    "Propose the requested synthetic calculator change as JSON.",
                )
                parser = ClaudeEventParser(capture_candidate=True)
                receipt = collect_native(
                    argv,
                    root,
                    env,
                    parser,
                    wall_seconds=max(0.1, deadline - time.monotonic()),
                    cancel=cancel,
                    output_bytes=256 * 1024,
                    pass_fds=(binary_fd, config_fd),
                )
                _unchanged(self.pin, binary_fd, time.monotonic() + 5)
                current = self.config.lstat()
                if (
                    (held.st_dev, held.st_ino) != (current.st_dev, current.st_ino)
                    or current.st_uid != os.getuid()
                    or stat.S_IMODE(current.st_mode) != 0o700
                ):
                    raise ProposalUnavailable("native_profile_changed")
                if hashlib.sha256(prompt.read_bytes()).hexdigest() != PROMPT_SHA256:
                    raise ProposalUnavailable("native_prompt_changed")
                candidate = None
                if receipt.status == "CANDIDATE" and parser.candidate_text is not None:
                    import json

                    try:
                        raw = json.loads(
                            parser.candidate_text, object_pairs_hook=_pairs, parse_constant=_invalid_constant
                        )
                        candidate = CodeProposal.model_validate(raw)
                    except (ValueError, ValidationError, RecursionError, ProtocolRejected):
                        return ProposalReceipt("REJECTED", "invalid_candidate_data", None, receipt)
                return ProposalReceipt(receipt.status, receipt.reason, candidate, receipt)
        except (OSError, NativeProbeUnavailable):
            raise ProposalUnavailable("native_launch_reference_changed") from None
        finally:
            for fd in (binary_fd, config_fd):
                if fd >= 0:
                    os.close(fd)
