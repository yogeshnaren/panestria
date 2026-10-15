"""Pinned, bounded CLI metadata probes; never execute a prompt or attached skill.

The binary reference and expected digest come from the trusted local controller.
Inspection is not a sandbox certificate or proof of usable subscription quota.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import selectors
import stat
import subprocess
import tempfile
import time
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from panestria.brokers.harness.event_parser import CLAUDE_VERSION
from panestria.brokers.harness.process_runner import _terminate
from panestria.contracts.native import NativeCompatibilityManifest, SkillMember

ARCHIVE_SHA256 = "bf9178cbd7800852e0167452900659f5a8238eb71754aa3b7944117ef35ceba6"
SKILL_ROOT = "agentos-skills/skills/claude-code-worker/"
SKILL_MEMBERS = {
    "SKILL.md": "26f2379722d31f6103fe754361f1473fa97aad8f6f53724652ffaa9524345c4b",
    "references/flag-profile.md": "dec4b7a48a1ae33e5b70f72cc052706f8c058db91cec70893176c1de5d2dd09b",
    "scripts/run_worker.py": "860f2a8abebc67b3911f23f30494fe6acf7785f6961a4cc8c5b09b2d4860829b",
    "scripts/prepare_worktree.py": "34b77e28ffbbc9439f3c17f5b598c9c2f95b5a7737e3bfbe84c1da64c8802eb4",
}
VISIBLE_CONTROLS = frozenset(
    {
        "--safe-mode",
        "--restricted",
        "--tools",
        "--disallowedTools",
        "--strict-mcp-config",
        "--settings",
        "--permission-mode",
        "--permission-prompts",
        "--no-session-persistence",
        "--output-format",
        "--max-budget-usd",
    }
)
PROBE_PREFIX = ("--safe-mode", "--restricted")
MAX_OUTPUT = 128 * 1024
MAX_BINARY = 512 * 1024**2
ERROR_CODES = frozenset(
    {
        "metadata_timeout",
        "metadata_output_limit",
        "metadata_unavailable",
        "invalid_probe_reference",
        "skill_archive_invalid",
        "skill_archive_mismatch",
        "skill_member_invalid",
        "skill_member_mismatch",
        "binary_size_or_deadline",
        "binary_pin_changed",
        "binary_reference_unsafe",
        "auth_metadata_invalid",
        "auth_metadata_exit_mismatch",
        "cli_version_mismatch",
        "advertised_controls_missing",
        "config_reference_changed",
    }
)


class NativeProbeUnavailable(Exception):
    """Messages are static codes, never raw CLI output, paths or auth metadata."""

    def __init__(self, code: str) -> None:
        self.code = code if code in ERROR_CODES else "metadata_unavailable"
        super().__init__(self.code)


@dataclass(frozen=True)
class BinaryPin:
    path: Path
    sha256: str


@dataclass(frozen=True)
class MetadataOutput:
    returncode: int
    stdout: bytes


class MetadataRunner(Protocol):
    def __call__(
        self,
        binary_fd: int,
        args: tuple[str, ...],
        cwd: Path,
        env: dict[str, str],
        deadline: float,
        config_fd: int | None,
    ) -> MetadataOutput: ...


def run_metadata(
    binary_fd: int,
    args: tuple[str, ...],
    cwd: Path,
    env: dict[str, str],
    deadline: float,
    config_fd: int | None,
) -> MetadataOutput:
    """Linux fd-bound execution prevents a replaced pathname selecting a new CLI."""
    if time.monotonic() >= deadline:
        raise NativeProbeUnavailable("metadata_timeout")
    fds = (binary_fd,) if config_fd is None else (binary_fd, config_fd)
    process = subprocess.Popen(
        (f"/proc/self/fd/{binary_fd}", *args),
        cwd=cwd,
        env=env,
        pass_fds=fds,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    assert process.stdout is not None and process.stderr is not None
    stdout = bytearray()
    total = 0
    try:
        with selectors.DefaultSelector() as selector:
            for name, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, name)
            while selector.get_map() or process.poll() is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise NativeProbeUnavailable("metadata_timeout")
                for key, _ in selector.select(min(0.05, remaining)):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    total += len(chunk)
                    if total > MAX_OUTPUT:
                        raise NativeProbeUnavailable("metadata_output_limit")
                    if key.data == "stdout":
                        stdout.extend(chunk)
                if not selector.get_map():
                    time.sleep(min(0.01, max(0, deadline - time.monotonic())))
        return MetadataOutput(process.wait(timeout=1), bytes(stdout))
    finally:
        _terminate(process)
        process.stdout.close()
        process.stderr.close()


def inventory_skill(archive: Path) -> tuple[SkillMember, ...]:
    """Read verified members as reference data; extract and execute nothing."""
    descriptor = os.open(archive, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise NativeProbeUnavailable("skill_archive_invalid")
        raw = stream.read(8 * 1024**2 + 1)
    if hashlib.sha256(raw).hexdigest() != ARCHIVE_SHA256:
        raise NativeProbeUnavailable("skill_archive_mismatch")
    members = []
    with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
        names = bundle.namelist()
        for name, expected in SKILL_MEMBERS.items():
            member = SKILL_ROOT + name
            if names.count(member) != 1:
                raise NativeProbeUnavailable("skill_member_invalid")
            digest = hashlib.sha256(bundle.read(member)).hexdigest()
            if digest != expected:
                raise NativeProbeUnavailable("skill_member_mismatch")
            members.append(SkillMember(member=member, sha256=digest))
    return tuple(members)


def _digest(fd: int, deadline: float) -> str:
    os.lseek(fd, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    total = 0
    while chunk := os.read(fd, 1024**2):
        total += len(chunk)
        if total > MAX_BINARY or time.monotonic() >= deadline:
            raise NativeProbeUnavailable("binary_size_or_deadline")
        digest.update(chunk)
    return digest.hexdigest()


def _unchanged(pin: BinaryPin, fd: int, deadline: float) -> None:
    current = pin.path.lstat()
    held = os.fstat(fd)
    if (
        (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino)
        or not stat.S_ISREG(current.st_mode)
        or current.st_mode & 0o022
        or current.st_uid not in (os.getuid(), 0)
        or not current.st_mode & 0o111
        or current.st_nlink != 1
        or not 0 < current.st_size <= MAX_BINARY
        or _digest(fd, deadline) != pin.sha256
    ):
        raise NativeProbeUnavailable("binary_pin_changed")


def _auth_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    body: dict[str, Any] = {}
    for key, value in pairs:
        if key in body:
            raise NativeProbeUnavailable("auth_metadata_invalid")
        body[key] = value
    return body


def _invalid_number(_value: str) -> None:
    raise NativeProbeUnavailable("auth_metadata_invalid")


def _auth_state(result: MetadataOutput) -> str:
    try:
        body = json.loads(result.stdout, object_pairs_hook=_auth_pairs, parse_constant=_invalid_number)
    except (ValueError, UnicodeError, RecursionError):
        raise NativeProbeUnavailable("auth_metadata_invalid") from None
    if not isinstance(body, dict) or type(body.get("loggedIn")) is not bool:
        raise NativeProbeUnavailable("auth_metadata_invalid")
    if not body["loggedIn"]:
        return "MISSING"
    if result.returncode != 0:
        raise NativeProbeUnavailable("auth_metadata_exit_mismatch")
    if body.get("authMethod") != "claude.ai" or body.get("apiProvider") != "firstParty":
        return "DENIED"
    # Discard email, account/organization IDs, token-like fields and raw output.
    return "SUBSCRIPTION"


class CliProfileProbe:
    def __init__(self, archive: Path, *, runner: MetadataRunner = run_metadata) -> None:
        self.archive, self.runner = archive, runner

    def inspect(
        self,
        pin: BinaryPin,
        config_directory: Path,
        *,
        wall_seconds: float = 20,
    ) -> NativeCompatibilityManifest:
        if (
            not 0 < wall_seconds <= 30
            or not pin.path.is_absolute()
            or re.fullmatch(r"[0-9a-f]{64}", pin.sha256) is None
        ):
            raise NativeProbeUnavailable("invalid_probe_reference")
        deadline = time.monotonic() + wall_seconds
        binary_fd = config_fd = None
        try:
            members = inventory_skill(self.archive)
            binary_fd = os.open(pin.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            binary_stat = os.fstat(binary_fd)
            if (
                not stat.S_ISREG(binary_stat.st_mode)
                or binary_stat.st_mode & 0o022
                or binary_stat.st_uid not in (os.getuid(), 0)
                or not binary_stat.st_mode & 0o111
                or binary_stat.st_nlink != 1
                or not 0 < binary_stat.st_size <= MAX_BINARY
            ):
                raise NativeProbeUnavailable("binary_reference_unsafe")
            _unchanged(pin, binary_fd, deadline)
            private = False
            try:
                canonical_config = config_directory.is_absolute() and config_directory.resolve() == config_directory
            except (OSError, RuntimeError):
                canonical_config = False
            if canonical_config:
                try:
                    candidate_fd = os.open(config_directory, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY)
                except OSError:
                    pass
                else:
                    info = os.fstat(candidate_fd)
                    if info.st_uid == os.getuid() and info.st_mode & 0o777 == 0o700:
                        config_fd, private = candidate_fd, True
                    else:
                        os.close(candidate_fd)
            with tempfile.TemporaryDirectory(prefix="panestria-cli-profile-") as folder:
                root = Path(folder)
                empty_config = root / "config"
                empty_config.mkdir(mode=0o700)
                env = {
                    "PATH": "/usr/bin:/bin",
                    "HOME": folder,
                    "LANG": "C.UTF-8",
                    "CLAUDE_CONFIG_DIR": str(empty_config),
                    "DISABLE_AUTOUPDATER": "1",
                    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                    "DISABLE_TELEMETRY": "1",
                    "DISABLE_ERROR_REPORTING": "1",
                }
                version = self.runner(binary_fd, (*PROBE_PREFIX, "--version"), root, env.copy(), deadline, None)
                _unchanged(pin, binary_fd, deadline)
                if version.returncode != 0 or version.stdout.strip() != f"{CLAUDE_VERSION} (Claude Code)".encode():
                    raise NativeProbeUnavailable("cli_version_mismatch")
                help_result = self.runner(binary_fd, (*PROBE_PREFIX, "--help"), root, env.copy(), deadline, None)
                _unchanged(pin, binary_fd, deadline)
                flags = frozenset(re.findall(rb"--[a-zA-Z][a-zA-Z0-9-]*", help_result.stdout))
                if help_result.returncode != 0 or any(flag.encode() not in flags for flag in VISIBLE_CONTROLS):
                    raise NativeProbeUnavailable("advertised_controls_missing")
                auth, status = "NOT_INSPECTED", "CONFIG_UNSAFE"
                if config_fd is not None:
                    env["CLAUDE_CONFIG_DIR"] = f"/proc/self/fd/{config_fd}"
                    result = self.runner(
                        binary_fd,
                        (*PROBE_PREFIX, "auth", "status", "--json"),
                        root,
                        env.copy(),
                        deadline,
                        config_fd,
                    )
                    _unchanged(pin, binary_fd, deadline)
                    held, current = os.fstat(config_fd), config_directory.lstat()
                    if (
                        (held.st_dev, held.st_ino) != (current.st_dev, current.st_ino)
                        or current.st_uid != os.getuid()
                        or current.st_mode & 0o777 != 0o700
                    ):
                        raise NativeProbeUnavailable("config_reference_changed")
                    auth = _auth_state(result)
                    statuses = {"SUBSCRIPTION": "INSPECTED", "MISSING": "AUTH_REQUIRED", "DENIED": "AUTH_MODE_DENIED"}
                    status = statuses[auth]
                return NativeCompatibilityManifest.model_validate(
                    {
                        "observed_at": datetime.now(UTC),
                        "cli_version": CLAUDE_VERSION,
                        "binary_sha256": pin.sha256,
                        "help_sha256": hashlib.sha256(help_result.stdout).hexdigest(),
                        "advertised_controls": tuple(sorted(VISIBLE_CONTROLS)),
                        "skills_archive_sha256": ARCHIVE_SHA256,
                        "skill_members": members,
                        "config_private": private,
                        "status": status,
                        "auth_state": auth,
                    }
                )
        except NativeProbeUnavailable:
            raise
        except (OSError, ValueError, zipfile.BadZipFile, subprocess.SubprocessError):
            raise NativeProbeUnavailable("metadata_unavailable") from None
        finally:
            if config_fd is not None:
                os.close(config_fd)
            if binary_fd is not None:
                os.close(binary_fd)
