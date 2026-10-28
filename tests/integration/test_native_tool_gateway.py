"""Reviewed gateway component tests; synthetic authority is not kernel integration."""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import threading
import time
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from panestria.contracts.native_tools import ToolRequest, ToolScope
from panestria.sandbox.native_tool_gateway import (
    GatewayRejected,
    NativeCommandRegistry,
    NativeToolGateway,
    ReviewedCommand,
    ToolPermit,
)
from panestria.sandbox.native_tool_input import MAGIC, decode_frame
from panestria.sandbox.profiles import ReadOnlyMount, SandboxProfile
from panestria.sandbox.runner import DockerSandbox, SandboxReceipt


class SyntheticAuthority:
    """Exercise the controller seam only. No claim of durable replay fencing."""

    def __init__(self, expected: ToolPermit) -> None:
        self.expected = expected
        self.claimed = False
        self.revoked = threading.Event()

    def claim(self, permit: ToolPermit) -> None:
        if permit != self.expected or self.claimed:
            raise ValueError("denied synthetic claim")
        self.claimed = True

    def check(self, permit: ToolPermit) -> None:
        if permit != self.expected or not self.claimed or self.revoked.is_set():
            raise ValueError("denied synthetic scope")


def setup(
    tmp_path: Path, code: str = "print('tool-ok')", *, edit: bool = False, seconds: float = 15
) -> tuple[NativeCommandRegistry, ToolRequest, ToolPermit, SyntheticAuthority]:
    root = tmp_path / "attempts"
    workspace = root / "candidate"
    workspace.mkdir(parents=True)
    protected = tmp_path / "protected.py"
    protected.write_text(code)
    protected.chmod(0o600)
    command = ReviewedCommand(
        "reviewed-command", protected, hashlib.sha256(protected.read_bytes()).hexdigest(), "edit" if edit else "read"
    )
    registry = NativeCommandRegistry((command,))
    request = ToolRequest(request_id=uuid4(), command_ref=command.ref, payload_json='{"text":"SYNTHETIC_PRIVATE_DATA"}')
    permit = ToolPermit(
        ToolScope(
            owner_id=uuid4(),
            project_id=uuid4(),
            task_id=uuid4(),
            attempt_id=uuid4(),
            lease_epoch=1,
            contract_sha256="ab" * 32,
            policy_ref="synthetic-policy",
        ),
        request.sha256(),
        registry.sha256(),
        workspace,
        SandboxProfile(
            name="scoped-code-edit" if edit else "restricted-offline",
            uid=os.getuid(),
            gid=os.getgid(),
            stdin_mode="native-frame-v1",
        ),
        time.monotonic() + seconds,
    )
    return registry, request, permit, SyntheticAuthority(permit)


class FakeRunner(DockerSandbox):
    def __init__(self, root: Path, mounts: tuple[ReadOnlyMount, ...]) -> None:
        super().__init__(root, runtime_mounts=mounts)
        self.started = False

    def run(
        self,
        workspace: Path,
        argv: tuple[str, ...],
        profile: SandboxProfile,
        *,
        attempt_id: str | None = None,
        cancel: threading.Event | None = None,
        input_frame: bytes | None = None,
    ) -> SandboxReceipt:
        self.started = True
        assert cancel is not None
        assert "SYNTHETIC_PRIVATE_DATA" not in repr(argv)
        assert argv[:3] == ("/usr/local/bin/python", "-I", "/runtime/native-launch.py")
        by_destination = {mount.destination: mount.source for mount in self.mounts}
        assert set(by_destination) == {
            "/runtime/native-launch.py",
            "/runtime/native-input.py",
            "/runtime/panestria-no-network.py",
        }
        assert input_frame is not None
        frame = decode_frame(io.BytesIO(input_frame), script_sha256=argv[3], request_sha256=argv[4])
        assert json.loads(frame.request)["payload_json"] == '{"text":"SYNTHETIC_PRIVATE_DATA"}'
        return SandboxReceipt("ef" * 32, profile.sha256(), "cd" * 32, 0, "completed", b"ok", 0.01, False)


def test_reviewed_input_is_snapshotted_and_claimed_before_execution(tmp_path: Path) -> None:
    registry, request, permit, authority = setup(tmp_path)
    original = registry.commands[0].script
    sources: list[Path] = []

    def factory(root: Path, mounts: tuple[ReadOnlyMount, ...]) -> DockerSandbox:
        sources.extend(mount.source for mount in mounts[:2])
        original.write_text("raise RuntimeError('changed after snapshot')")
        runner = FakeRunner(root, mounts)
        original_run = runner.run

        def run(*args: object, **kwargs: object) -> SandboxReceipt:
            assert authority.claimed
            return original_run(*args, **kwargs)  # type: ignore[arg-type]

        runner.run = run  # type: ignore[method-assign]
        return runner

    gateway = NativeToolGateway(permit.workspace.parent, registry, authority, runner_factory=factory)
    receipt = gateway.execute(request, permit)
    assert receipt.outcome == "completed"
    assert receipt.scope_sha256 == permit.scope.sha256()
    assert all(source.exists() for source in sources) and original not in sources
    assert {source.name for source in sources} == {"native_tool_launch.py", "native_tool_input.py"}
    with pytest.raises(GatewayRejected, match="command_digest_mismatch"):
        gateway.execute(request, permit)


def test_private_staging_cannot_be_redirected_into_the_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, request, permit, authority = setup(tmp_path)
    monkeypatch.setattr("tempfile.tempdir", str(permit.workspace))

    def forbidden(*args, **kwargs):
        raise AssertionError("gateway must not allocate host input stages")

    monkeypatch.setattr("tempfile.TemporaryDirectory", forbidden)

    def factory(root: Path, mounts: tuple[ReadOnlyMount, ...]) -> DockerSandbox:
        assert all(not mount.source.is_relative_to(permit.workspace) for mount in mounts)
        return FakeRunner(root, mounts)

    receipt = NativeToolGateway(permit.workspace.parent, registry, authority, runner_factory=factory).execute(
        request, permit
    )
    assert receipt.outcome == "completed"
    assert list(permit.workspace.iterdir()) == []


@pytest.mark.parametrize("name", ["mock-no-network", "read-only-research", "restricted-offline"])
def test_edit_commands_require_the_scoped_edit_profile(tmp_path: Path, name: str) -> None:
    registry, request, permit, authority = setup(tmp_path, edit=True)
    wrong = replace(permit, profile=replace(permit.profile, name=name))  # type: ignore[arg-type]
    gateway = NativeToolGateway(permit.workspace.parent, registry, authority, runner_factory=FakeRunner)
    with pytest.raises(GatewayRejected, match="command_access_mismatch"):
        gateway.execute(request, wrong)
    assert not authority.claimed


@pytest.mark.parametrize(
    "raw",
    [
        '{"x":1,"x":2}',
        '{"x":NaN}',
        '{"x":1e999}',
        "[]",
        '{"x":',
        '{"x":' + "[" * 18 + "0" + "]" * 18 + "}",
        '{"x":"' + "a" * 32768 + '"}',
    ],
)
def test_worker_payload_is_bounded_strict_json(raw: str) -> None:
    with pytest.raises(ValidationError):
        ToolRequest(request_id=uuid4(), command_ref="reviewed-command", payload_json=raw)


@pytest.mark.parametrize("field", ["argv", "env", "workspace", "scope", "approved", "profile", "deadline"])
def test_worker_cannot_submit_controller_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        ToolRequest.model_validate(
            {"request_id": uuid4(), "command_ref": "reviewed-command", "payload_json": "{}", field: "forged"}
        )


@pytest.mark.parametrize(
    "field", ["owner_id", "project_id", "task_id", "attempt_id", "lease_epoch", "contract_sha256", "policy_ref"]
)
def test_wrong_scope_never_runs_a_container(tmp_path: Path, field: str) -> None:
    registry, request, permit, authority = setup(tmp_path)
    changed: object = (
        uuid4()
        if field.endswith("_id")
        else (2 if field == "lease_epoch" else "cd" * 32 if field == "contract_sha256" else "another-policy")
    )
    wrong = replace(permit, scope=permit.scope.model_copy(update={field: changed}))
    gateway = NativeToolGateway(permit.workspace.parent, registry, authority, runner_factory=FakeRunner)
    with pytest.raises(GatewayRejected, match="dispatch_claim_denied"):
        gateway.execute(request, wrong)
    assert not authority.claimed


def test_request_registry_and_access_bindings_fail_closed(tmp_path: Path) -> None:
    registry, request, permit, authority = setup(tmp_path)
    gateway = NativeToolGateway(permit.workspace.parent, registry, authority, runner_factory=FakeRunner)
    for wrong in (replace(permit, request_sha256="ab" * 32), replace(permit, registry_sha256="cd" * 32)):
        with pytest.raises(GatewayRejected, match="permit_binding_mismatch"):
            gateway.execute(request, wrong)
    unknown = ToolRequest(request_id=uuid4(), command_ref="worker-invented-command", payload_json="{}")
    with pytest.raises(GatewayRejected, match="unregistered_command"):
        gateway.execute(unknown, replace(permit, request_sha256=unknown.sha256()))
    with pytest.raises(GatewayRejected, match="command_access_mismatch"):
        gateway.execute(request, replace(permit, profile=replace(permit.profile, name="scoped-code-edit")))
    assert not authority.claimed


@pytest.mark.parametrize("change", ["symlink", "symlink-loop", "hardlink", "writable", "workspace", "tamper"])
def test_unreviewed_or_unsafe_scripts_fail_before_claim(tmp_path: Path, change: str) -> None:
    registry, request, permit, authority = setup(tmp_path)
    script = registry.commands[0].script
    if change == "symlink":
        original = script.with_suffix(".original")
        script.rename(original)
        script.symlink_to(original)
    elif change == "symlink-loop":
        script.unlink()
        script.symlink_to(script)
    elif change == "hardlink":
        os.link(script, script.with_suffix(".link"))
    elif change == "writable":
        script.chmod(0o666)
    elif change == "workspace":
        moved = permit.workspace / "untrusted.py"
        script.rename(moved)
        registry = NativeCommandRegistry((replace(registry.commands[0], script=moved),))
    else:
        script.write_text("print('unreviewed')")
    gateway = NativeToolGateway(permit.workspace.parent, registry, authority, runner_factory=FakeRunner)
    with pytest.raises(GatewayRejected):
        gateway.execute(request, permit)
    assert not authority.claimed


@pytest.mark.parametrize("condition", ["pre-cancel", "nan-deadline", "expired", "outside", "workspace-link"])
def test_cancel_deadline_and_workspace_guards_refuse_before_claim(tmp_path: Path, condition: str) -> None:
    registry, request, permit, authority = setup(tmp_path)
    cancel = threading.Event()
    if condition == "pre-cancel":
        cancel.set()
    elif condition == "nan-deadline":
        permit = replace(permit, deadline_monotonic=float("nan"))
    elif condition == "expired":
        permit = replace(permit, deadline_monotonic=time.monotonic() - 1)
    elif condition == "outside":
        permit = replace(permit, workspace=tmp_path)
    else:
        link = permit.workspace.parent / "link"
        link.symlink_to(permit.workspace, target_is_directory=True)
        permit = replace(permit, workspace=link)
    gateway = NativeToolGateway(tmp_path / "attempts", registry, authority, runner_factory=FakeRunner)
    with pytest.raises(GatewayRejected):
        gateway.execute(request, permit, cancel=cancel)
    assert not authority.claimed


def test_payload_escaping_also_bounds_the_request_envelope(tmp_path: Path) -> None:
    registry, _, permit, authority = setup(tmp_path)
    request = ToolRequest(
        request_id=uuid4(), command_ref="reviewed-command", payload_json=json.dumps({"x": "\\" * 16378})
    )
    gateway = NativeToolGateway(permit.workspace.parent, registry, authority, runner_factory=FakeRunner)
    with pytest.raises(GatewayRejected, match="tool_request_limit"):
        gateway.execute(request, permit)
    assert not authority.claimed


def test_replay_requires_a_new_durable_controller_claim(tmp_path: Path) -> None:
    registry, request, permit, authority = setup(tmp_path)
    gateway = NativeToolGateway(permit.workspace.parent, registry, authority, runner_factory=FakeRunner)
    assert gateway.execute(request, permit).outcome == "completed"
    with pytest.raises(GatewayRejected, match="dispatch_claim_denied"):
        gateway.execute(request, permit)


@pytest.mark.parametrize("revoke", [False, True])
def test_runtime_exception_is_unknown_and_has_no_raw_diagnostic(tmp_path: Path, revoke: bool) -> None:
    registry, request, permit, authority = setup(tmp_path)

    class BrokenRunner(FakeRunner):
        def run(self, *args: object, **kwargs: object) -> SandboxReceipt:
            if revoke:
                authority.revoked.set()
            raise RuntimeError("SYNTHETIC_PRIVATE_DATA/host/path")

    receipt = NativeToolGateway(permit.workspace.parent, registry, authority, runner_factory=BrokenRunner).execute(
        request, permit
    )
    assert receipt.outcome == "unknown" and receipt.sandbox is None
    assert receipt.unconfirmed_reason == "sandbox_return_unconfirmed"
    assert "SYNTHETIC_PRIVATE_DATA" not in repr(receipt)


def test_stalled_authority_check_does_not_start_or_authorize_a_worker(tmp_path: Path) -> None:
    registry, request, permit, _ = setup(tmp_path)
    release = threading.Event()
    finished = threading.Event()

    class StalledAuthority(SyntheticAuthority):
        def check(self, permit: ToolPermit) -> None:
            try:
                release.wait(timeout=5)
            finally:
                finished.set()

    started = time.monotonic()
    try:
        receipt = NativeToolGateway(
            permit.workspace.parent, registry, StalledAuthority(permit), runner_factory=FakeRunner
        ).execute(request, permit)
        assert receipt.outcome == "unknown" and receipt.sandbox is None
        assert receipt.unconfirmed_reason == "authority_observation_deadline"
        assert time.monotonic() - started < 2
    finally:
        release.set()
        assert finished.wait(timeout=2)


@pytest.mark.parametrize("condition", ["cancelled", "expired", "revoked"])
def test_authority_changes_during_claim_never_start_the_worker(tmp_path: Path, condition: str) -> None:
    registry, request, permit, _ = setup(tmp_path)
    cancel = threading.Event()

    class ChangeDuringClaim(SyntheticAuthority):
        def claim(self, permit: ToolPermit) -> None:
            super().claim(permit)
            if condition == "cancelled":
                cancel.set()
            elif condition == "revoked":
                self.revoked.set()
            else:
                time.sleep(0.2)

    if condition == "expired":
        permit = replace(permit, deadline_monotonic=time.monotonic() + 0.15)
    authority = ChangeDuringClaim(permit)
    runner: FakeRunner | None = None

    def factory(root: Path, mounts: tuple[ReadOnlyMount, ...]) -> DockerSandbox:
        nonlocal runner
        runner = FakeRunner(root, mounts)
        return runner

    receipt = NativeToolGateway(permit.workspace.parent, registry, authority, runner_factory=factory).execute(
        request, permit, cancel=cancel
    )
    assert runner is not None and not runner.started
    assert (
        receipt.outcome
        == {"cancelled": "cancelled", "expired": "deadline_exceeded", "revoked": "authority_revoked"}[condition]
    )


@pytest.mark.docker_boundary
@pytest.mark.live
@pytest.mark.parametrize("edit", [False, True])
def test_actual_gateway_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, edit: bool, record_property: pytest.RecordProperty
) -> None:
    code = """
import os, socket
from pathlib import Path
assert 'SYNTHETIC_PRIVATE_DATA' not in repr(__import__('sys').argv)
assert PANESTRIA_TOOL_REQUEST['payload_json'] == '{"text":"SYNTHETIC_PRIVATE_DATA"}'
assert __name__ == '__main__' and __package__ is None and __spec__ is None
assert __file__ == __import__('sys').argv[0] and __file__.startswith('/virtual/panestria-command-')
assert not Path(__file__).exists()
assert not Path('/runtime/native-command.py').exists() and not Path('/runtime/native-request.json').exists()
assert not any(key in os.environ for key in ('ANTHROPIC_API_KEY','OPENAI_API_KEY','PANESTRIA_DATABASE_URL'))
assert not Path(HOST_SENTINEL_PATH).exists()
for target in ('/etc/must-not-write','/runtime/native-launch.py','/runtime/native-input.py'):
    try: Path(target).write_text('forged')
    except OSError: pass
    else: raise AssertionError('protected mount writable')
try: socket.socket(socket.AF_INET,socket.SOCK_STREAM)
except PermissionError: pass
else: raise AssertionError('network available')
try: Path('/workspace/result.txt').write_text('candidate')
except OSError:
    assert READ_ONLY
else:
    assert not READ_ONLY
print('gateway-boundary-ok')
""".replace("READ_ONLY", repr(not edit)).replace("HOST_SENTINEL_PATH", repr(str(tmp_path / "synthetic-host-secret")))
    registry, request, permit, authority = setup(tmp_path, code, edit=edit)
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "PANESTRIA_DATABASE_URL"):
        monkeypatch.setenv(key, "SYNTHETIC_HOST_SECRET_SENTINEL")
    # This existing file must not enter the runtime merely because it is next
    # to a reviewed script. It is never mounted by the gateway.
    sentinel = tmp_path / "synthetic-host-secret"
    sentinel.write_text("SYNTHETIC_HOST_SECRET_SENTINEL")
    receipt = NativeToolGateway(permit.workspace.parent, registry, authority).execute(request, permit)
    assert receipt.outcome == "completed" and receipt.sandbox is not None
    assert receipt.sandbox.output == b"gateway-boundary-ok\n"
    assert (permit.workspace / "result.txt").exists() == edit
    assert subprocess.run(["docker", "inspect", receipt.sandbox.container_id], capture_output=True).returncode != 0
    assert sentinel.read_text() == "SYNTHETIC_HOST_SECRET_SENTINEL"
    record_property("gate_case_id", "AOS-010-TC03")
    record_property("source_clauses", "AOS-010-AC03")
    record_property("execution_mode", "OS_BOUNDARY_SYNTHETIC_AUTHORITY")
    record_property("profile_sha256", receipt.sandbox.profile_sha256)
    record_property("effective_config_sha256", receipt.sandbox.effective_config_sha256)


@pytest.mark.docker_boundary
@pytest.mark.live
@pytest.mark.parametrize("section", ["script", "request"])
def test_actual_launcher_rechecks_snapshot_before_executing_code(tmp_path: Path, section: str) -> None:
    registry, request, permit, authority = setup(
        tmp_path, "open('/workspace/must-not-exist','w').write('bad')", edit=True
    )

    def mutate(root: Path, mounts: tuple[ReadOnlyMount, ...]) -> DockerSandbox:
        class TamperedFrame(DockerSandbox):
            def run(self, workspace, argv, profile, *, input_frame=None, **kwargs):
                changed = bytearray(input_frame)
                offset = len(MAGIC) + 8
                if section == "request":
                    offset += int.from_bytes(changed[len(MAGIC) : len(MAGIC) + 4], "big")
                changed[offset] ^= 1
                return super().run(workspace, argv, profile, input_frame=bytes(changed), **kwargs)

        return TamperedFrame(root, runtime_mounts=mounts)

    receipt = NativeToolGateway(permit.workspace.parent, registry, authority, runner_factory=mutate).execute(
        request, permit
    )
    assert receipt.outcome == "failed" and receipt.sandbox is not None
    assert receipt.sandbox.output == b"native_tool_input_mismatch\n"
    assert not (permit.workspace / "must-not-exist").exists()
    assert subprocess.run(["docker", "inspect", receipt.sandbox.container_id], capture_output=True).returncode != 0


@pytest.mark.docker_boundary
@pytest.mark.live
@pytest.mark.parametrize("condition", ["revoked", "cancelled", "deadline"])
def test_actual_gateway_stops_on_authority_cancel_or_deadline(tmp_path: Path, condition: str) -> None:
    registry, request, permit, authority = setup(tmp_path, "import time;time.sleep(60)", seconds=15)
    cancel = threading.Event()
    callback = authority.revoked.set if condition == "revoked" else cancel.set
    if condition == "deadline":
        permit = replace(permit, deadline_monotonic=time.monotonic() + 0.8)
        authority.expected = permit
        timer = None
    else:
        timer = threading.Timer(0.8, callback)
        timer.start()
    started = time.monotonic()
    try:
        receipt = NativeToolGateway(permit.workspace.parent, registry, authority).execute(
            request, permit, cancel=cancel
        )
    finally:
        if timer is not None:
            timer.cancel()
            timer.join()
    assert (
        receipt.outcome
        == {"revoked": "authority_revoked", "cancelled": "cancelled", "deadline": "deadline_exceeded"}[condition]
    )
    assert time.monotonic() - started < 5
    assert receipt.sandbox is not None and receipt.sandbox.exit_code is not None
    assert subprocess.run(["docker", "inspect", receipt.sandbox.container_id], capture_output=True).returncode != 0
