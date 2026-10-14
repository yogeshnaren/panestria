"""Probe contracts and real subprocess limits, separate from native conformance."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from panestria.brokers.harness.cli_profile import (
    ARCHIVE_SHA256,
    PROBE_PREFIX,
    VISIBLE_CONTROLS,
    BinaryPin,
    CliProfileProbe,
    MetadataOutput,
    NativeProbeUnavailable,
    inventory_skill,
    run_metadata,
)
from panestria.cli.main import app

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "docs/specification/attachments/agentos-skills-v0.1.0.zip"
SENTINEL = "private-account-and-token-synthetic-sentinel"


@pytest.fixture(autouse=True)
def _case(record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-010-TC01")
    record_property("source_clauses", "AOS-010-F01,AOS-010-F02,AOS-010-F03")
    record_property("execution_mode", "HERMETIC_WITH_OS_PROCESS_LIMIT_CASES")


@pytest.fixture
def pin(tmp_path: Path) -> BinaryPin:
    # A trusted test binary plus an injected metadata transport is not live Claude.
    binary = tmp_path / "pinned-test-binary"
    shutil.copyfile(Path(sys.executable).resolve(), binary)
    binary.chmod(0o700)
    return BinaryPin(binary, hashlib.sha256(binary.read_bytes()).hexdigest())


@pytest.fixture
def config(tmp_path: Path) -> Path:
    directory = tmp_path / "native-config"
    directory.mkdir(mode=0o700)
    return directory


class FakeMetadata:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], dict[str, str]]] = []
        self.version = b"2.1.273 (Claude Code)\n"
        self.help = "\n".join(sorted(VISIBLE_CONTROLS)).encode()
        self.auth = json.dumps(
            {
                "loggedIn": True,
                "authMethod": "claude.ai",
                "apiProvider": "firstParty",
                "email": SENTINEL,
                "accountId": SENTINEL,
                "organizationId": SENTINEL,
                "token": SENTINEL,
            }
        ).encode()
        self.auth_exit = 0

    def __call__(
        self,
        binary_fd: int,
        args: tuple[str, ...],
        cwd: Path,
        env: dict[str, str],
        deadline: float,
        config_fd: int | None,
    ) -> MetadataOutput:
        assert os.fstat(binary_fd).st_size > 0
        assert args[:2] == PROBE_PREFIX
        assert not (cwd / "CLAUDE.md").exists() and not (cwd / ".claude").exists()
        assert time.monotonic() < deadline
        self.calls.append((args, env))
        if args[-1] == "--version":
            return MetadataOutput(0, self.version)
        if args[-1] == "--help":
            return MetadataOutput(0, self.help)
        assert args[2:] == ("auth", "status", "--json") and config_fd is not None
        assert env["CLAUDE_CONFIG_DIR"] == f"/proc/self/fd/{config_fd}"
        assert os.fstat(config_fd).st_mode & 0o077 == 0
        return MetadataOutput(self.auth_exit, self.auth)


def test_verified_skill_inventory_never_extracts_or_executes(tmp_path: Path) -> None:
    members = inventory_skill(ARCHIVE)
    assert len(members) == 4
    assert {member.member.rsplit("/", 1)[-1] for member in members} == {
        "SKILL.md",
        "flag-profile.md",
        "run_worker.py",
        "prepare_worktree.py",
    }
    assert hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() == ARCHIVE_SHA256
    altered = tmp_path / "altered.zip"
    altered.write_bytes(ARCHIVE.read_bytes() + SENTINEL.encode())
    with pytest.raises(NativeProbeUnavailable, match="skill_archive_mismatch") as caught:
        inventory_skill(altered)
    assert SENTINEL not in str(caught.value)


def test_subscription_metadata_is_redacted_and_never_grants_execution(
    pin: BinaryPin,
    config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "HTTPS_PROXY", "CLAUDE_CODE_PROCESS_WRAPPER"):
        monkeypatch.setenv(name, SENTINEL)
    transport = FakeMetadata()
    manifest = CliProfileProbe(ARCHIVE, runner=transport).inspect(pin, config)
    assert manifest.status == "INSPECTED" and manifest.auth_state == "SUBSCRIPTION"
    assert manifest.config_private and len(transport.calls) == 3
    assert manifest.conformance == "NOT_RUN"
    assert not manifest.execution_authorized and not manifest.inference_verified
    assert SENTINEL not in manifest.model_dump_json() and SENTINEL not in repr(manifest)
    for args, env in transport.calls:
        assert "-p" not in args and "--bare" not in args
        assert SENTINEL not in repr(env)
        assert env["DISABLE_AUTOUPDATER"] == "1" and env["DISABLE_TELEMETRY"] == "1"
    with pytest.raises(ValidationError):
        type(manifest).model_validate({**manifest.model_dump(), "execution_authorized": True})


@pytest.mark.parametrize("mode", [0o755, 0o775, 0o777, 0o600])
def test_nonprivate_config_does_not_run_auth(pin: BinaryPin, config: Path, mode: int) -> None:
    config.chmod(mode)
    transport = FakeMetadata()
    result = CliProfileProbe(ARCHIVE, runner=transport).inspect(pin, config)
    assert result.status == "CONFIG_UNSAFE" and result.auth_state == "NOT_INSPECTED"
    assert len(transport.calls) == 2


def test_symlink_or_missing_config_is_not_an_auth_handle(pin: BinaryPin, config: Path, tmp_path: Path) -> None:
    linked = tmp_path / "linked-config"
    linked.symlink_to(config, target_is_directory=True)
    for directory in (linked, tmp_path / "missing-config", Path("relative")):
        transport = FakeMetadata()
        assert CliProfileProbe(ARCHIVE, runner=transport).inspect(pin, directory).status == "CONFIG_UNSAFE"
        assert len(transport.calls) == 2


@pytest.mark.parametrize(
    "auth,expected",
    [
        ({"loggedIn": False}, "AUTH_REQUIRED"),
        ({"loggedIn": True, "authMethod": "api_key", "apiProvider": "firstParty"}, "AUTH_MODE_DENIED"),
        ({"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "bedrock"}, "AUTH_MODE_DENIED"),
    ],
)
def test_missing_login_or_other_auth_never_falls_back(
    pin: BinaryPin,
    config: Path,
    auth: dict[str, object],
    expected: str,
) -> None:
    transport = FakeMetadata()
    transport.auth = json.dumps(auth).encode()
    result = CliProfileProbe(ARCHIVE, runner=transport).inspect(pin, config)
    assert result.status == expected and not result.execution_authorized
    assert len(transport.calls) == 3


@pytest.mark.parametrize(
    "raw",
    [
        b"not-json",
        b'{"loggedIn":true,"loggedIn":false}',
        b'{"loggedIn":"true"}',
        b'{"loggedIn":true,"ignored":NaN}',
        b"[]",
        b"\xff",
        b"{}",
    ],
)
def test_bad_auth_metadata_fails_closed(pin: BinaryPin, config: Path, raw: bytes) -> None:
    transport = FakeMetadata()
    transport.auth = raw
    with pytest.raises(NativeProbeUnavailable, match="auth_metadata_invalid"):
        CliProfileProbe(ARCHIVE, runner=transport).inspect(pin, config)


def test_auth_success_with_error_exit_is_not_accepted(pin: BinaryPin, config: Path) -> None:
    transport = FakeMetadata()
    transport.auth_exit = 1
    with pytest.raises(NativeProbeUnavailable, match="auth_metadata_exit_mismatch"):
        CliProfileProbe(ARCHIVE, runner=transport).inspect(pin, config)


@pytest.mark.parametrize("version", [b"2.1.274 (Claude Code)", b"2.1.273 fake", SENTINEL.encode()])
def test_cli_drift_prevents_auth_probe(pin: BinaryPin, config: Path, version: bytes) -> None:
    transport = FakeMetadata()
    transport.version = version
    with pytest.raises(NativeProbeUnavailable, match="cli_version_mismatch") as caught:
        CliProfileProbe(ARCHIVE, runner=transport).inspect(pin, config)
    assert len(transport.calls) == 1 and SENTINEL not in str(caught.value)


def test_missing_advertised_control_and_binary_pin_changes_stop_probe(pin: BinaryPin, config: Path) -> None:
    transport = FakeMetadata()
    transport.help = transport.help.replace(b"--restricted", b"--another-control")
    with pytest.raises(NativeProbeUnavailable, match="advertised_controls_missing"):
        CliProfileProbe(ARCHIVE, runner=transport).inspect(pin, config)
    transport = FakeMetadata()
    with pytest.raises(NativeProbeUnavailable, match="binary_pin_changed"):
        CliProfileProbe(ARCHIVE, runner=transport).inspect(BinaryPin(pin.path, "ab" * 32), config)
    assert not transport.calls


def test_binary_replacement_between_metadata_commands_is_denied(pin: BinaryPin, config: Path) -> None:
    transport = FakeMetadata()

    def replace(
        binary_fd: int,
        args: tuple[str, ...],
        cwd: Path,
        env: dict[str, str],
        deadline: float,
        config_fd: int | None,
    ) -> MetadataOutput:
        result = transport(binary_fd, args, cwd, env, deadline, config_fd)
        replacement = pin.path.with_suffix(".new")
        replacement.write_bytes(pin.path.read_bytes())
        replacement.chmod(0o700)
        replacement.replace(pin.path)
        return result

    with pytest.raises(NativeProbeUnavailable, match="binary_pin_changed"):
        CliProfileProbe(ARCHIVE, runner=replace).inspect(pin, config)
    assert len(transport.calls) == 1


def test_unsafe_binary_or_symlink_is_denied_before_execution(pin: BinaryPin, config: Path) -> None:
    for mode in (0o777, 0o600):
        pin.path.chmod(mode)
        with pytest.raises(NativeProbeUnavailable, match="binary_reference_unsafe"):
            CliProfileProbe(ARCHIVE, runner=FakeMetadata()).inspect(pin, config)
    alias = pin.path.with_suffix(".link")
    alias.symlink_to(pin.path)
    with pytest.raises(NativeProbeUnavailable, match="metadata_unavailable"):
        CliProfileProbe(ARCHIVE, runner=FakeMetadata()).inspect(BinaryPin(alias, pin.sha256), config)


def test_real_metadata_process_deadline_and_output_caps(pin: BinaryPin, tmp_path: Path) -> None:
    descriptor = os.open(Path(sys.executable).resolve(), os.O_RDONLY)
    try:
        for args, reason in (
            (("-I", "-c", "import time; time.sleep(20)"), "metadata_timeout"),
            (("-I", "-c", "import sys; sys.stderr.write('x'*200000)"), "metadata_output_limit"),
            (("-I", "-c", "import sys; sys.stdout.write('x'*200000)"), "metadata_output_limit"),
            (("-I", "-c", "import os,time; os.close(1); os.close(2); time.sleep(20)"), "metadata_timeout"),
        ):
            started = time.monotonic()
            with pytest.raises(NativeProbeUnavailable, match=reason):
                run_metadata(
                    descriptor,
                    args,
                    tmp_path,
                    {"PATH": "/usr/bin:/bin", "LD_LIBRARY_PATH": str(Path(sys.base_prefix) / "lib")},
                    started + 0.3,
                    None,
                )
            assert time.monotonic() - started < 3
    finally:
        os.close(descriptor)


@pytest.mark.parametrize("change", ["permissions", "replacement"])
def test_config_replaced_or_permissions_widened_during_auth_is_denied(
    pin: BinaryPin,
    config: Path,
    change: str,
) -> None:
    transport = FakeMetadata()

    def widen(
        binary_fd: int,
        args: tuple[str, ...],
        cwd: Path,
        env: dict[str, str],
        deadline: float,
        config_fd: int | None,
    ) -> MetadataOutput:
        result = transport(binary_fd, args, cwd, env, deadline, config_fd)
        if config_fd is not None:
            if change == "permissions":
                config.chmod(0o775)
            else:
                config.rename(config.with_name("old-config"))
                config.mkdir(mode=0o700)
        return result

    with pytest.raises(NativeProbeUnavailable, match="config_reference_changed"):
        CliProfileProbe(ARCHIVE, runner=widen).inspect(pin, config)


def test_cli_inspection_failure_is_redacted(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "native",
            "inspect",
            "--binary",
            str(tmp_path / SENTINEL),
            "--expected-sha256",
            "ab" * 32,
            "--config-dir",
            str(tmp_path),
            "--skills-archive",
            str(ARCHIVE),
        ],
    )
    assert result.exit_code == 2 and "metadata_unavailable" in result.output
    assert SENTINEL not in result.output


def test_cli_success_and_unsafe_configuration_have_distinct_exit_codes(
    pin: BinaryPin,
    config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = FakeMetadata()
    monkeypatch.setattr(
        "panestria.cli.native.CliProfileProbe", lambda archive: CliProfileProbe(archive, runner=transport)
    )
    args = [
        "native",
        "inspect",
        "--binary",
        str(pin.path),
        "--expected-sha256",
        pin.sha256,
        "--config-dir",
        str(config),
        "--skills-archive",
        str(ARCHIVE),
    ]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0
    assert json.loads(result.output)["execution_authorized"] is False
    assert SENTINEL not in result.output
    config.chmod(0o775)
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 1 and json.loads(result.output)["status"] == "CONFIG_UNSAFE"


def test_config_symlink_loop_is_not_an_auth_handle(pin: BinaryPin, tmp_path: Path) -> None:
    path = tmp_path / "loop"
    path.symlink_to(path, target_is_directory=True)
    transport = FakeMetadata()
    assert CliProfileProbe(ARCHIVE, runner=transport).inspect(pin, path).status == "CONFIG_UNSAFE"
    assert len(transport.calls) == 2


def test_unrecognized_diagnostic_text_cannot_escape_error_codes() -> None:
    assert str(NativeProbeUnavailable(SENTINEL)) == "metadata_unavailable"
