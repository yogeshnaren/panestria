"""Explicit memory interface and actual automatic durable runner factory."""

import hashlib
import json
import time
from dataclasses import replace

import pytest
from test_native_tool_gateway import FakeRunner, setup
from test_registered_check_authority import configured as configured

from panestria.execution.registered_checks import RegisteredCheckController
from panestria.execution.tool_authority import DurableToolAuthority, tool_binding
from panestria.kernel.invocations import InvocationService
from panestria.kernel.sandbox_launches import SandboxLaunchService
from panestria.kernel.uow import UnitOfWork
from panestria.sandbox.native_tool_gateway import GatewayRejected, NativeCommandRegistry, NativeToolGateway, ToolPermit


def test_old_closed_profile_cannot_silently_adopt_memory_execution(tmp_path):
    registry, request, permit, authority = setup(tmp_path)
    permit = replace(permit, profile=replace(permit.profile, stdin_mode="closed"))
    with pytest.raises(GatewayRejected, match="tool_input_mode_denied"):
        NativeToolGateway(permit.workspace.parent, registry, authority, runner_factory=FakeRunner).execute(
            request, permit
        )
    assert not authority.claimed


def test_old_file_registry_digest_cannot_authorize_new_interface(tmp_path):
    registry, request, permit, authority = setup(tmp_path)
    command = registry.commands[0]
    old = hashlib.sha256(
        json.dumps(
            [{"ref": command.ref, "sha256": command.sha256, "access": command.access}],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert old != registry.sha256()
    with pytest.raises(GatewayRejected, match="permit_binding_mismatch"):
        NativeToolGateway(permit.workspace.parent, registry, authority).execute(
            request, replace(permit, registry_sha256=old)
        )
    assert not authority.claimed


@pytest.mark.parametrize("interface", ["file-v1", "python-memory-v2", None])
def test_unknown_or_old_execution_interface_rejects_before_claim(tmp_path, interface):
    registry, request, permit, authority = setup(tmp_path)
    registry = NativeCommandRegistry((replace(registry.commands[0], execution=interface),))
    permit = replace(permit, registry_sha256=registry.sha256())
    with pytest.raises(GatewayRejected, match="invalid_registry"):
        NativeToolGateway(permit.workspace.parent, registry, authority).execute(request, permit)
    assert not authority.claimed


def test_script_self_read_fails_without_file_staging_fallback(tmp_path):
    registry, request, permit, authority = setup(
        tmp_path,
        "from pathlib import Path\nPath(__file__).read_bytes()\nPath('/workspace/must-not-exist').write_text('bad')\n",
        edit=True,
    )
    result = NativeToolGateway(permit.workspace.parent, registry, authority).execute(request, permit)
    assert result.outcome == "failed" and result.sandbox.reason == "process_failed"
    assert b"/virtual/panestria-command-" in result.sandbox.output
    assert b"SYNTHETIC_PRIVATE_DATA" not in result.sandbox.output
    assert not (permit.workspace / "must-not-exist").exists()


def test_actual_python_module_identity_supports_annotations_and_dataclasses(tmp_path):
    code = '''from __future__ import annotations
import __main__,sys
from dataclasses import dataclass,fields
from typing import ClassVar
@dataclass
class Example:
    shared: ClassVar[int] = 7
    value: int = 1
assert [item.name for item in fields(Example)] == ['value']
assert __main__.Example is Example and sys.modules['__main__'].__dict__ is globals()
print('memory-module-ok')
'''
    registry, request, permit, authority = setup(tmp_path, code)
    result = NativeToolGateway(permit.workspace.parent, registry, authority).execute(request, permit)
    assert result.outcome == "completed" and result.sandbox.output == b"memory-module-ok\n"


def test_actual_default_gateway_uses_durable_factory_and_retains_launch_scope(configured):
    task, args = configured
    controller = RegisteredCheckController(*args)
    permit = ToolPermit(
        controller.scope,
        controller.request.sha256(),
        controller.registry.sha256(),
        controller.snapshot.directory,
        controller.profile,
        time.monotonic() + 10,
    )
    binding = tool_binding(permit)
    with controller.connect() as c:
        identity = InvocationService().prepare(UnitOfWork(c), controller.actor, binding, "automatic-factory-proof")
        before = c.execute("SELECT state FROM panestria.task WHERE id=%s", (task["task"],)).fetchone()
    authority = DurableToolAuthority(controller.connect, controller.actor, identity)
    result = NativeToolGateway(controller.snapshot.directory.parent, controller.registry, authority).execute(
        controller.request, permit
    )
    assert result.outcome == "completed" and result.sandbox.exit_code == 0
    with controller.connect() as c:
        intent = SandboxLaunchService().read(UnitOfWork(c), controller.actor, binding, identity)
        assert (intent.binding_sha256, intent.scope_sha256) == (binding.sha256(), controller.scope.sha256())
        assert c.execute("SELECT state FROM panestria.task WHERE id=%s", (task["task"],)).fetchone() == before
        # Execution alone supplies no verifier or owner decision receipt.
        InvocationService().finish(UnitOfWork(c), controller.actor, binding, identity, None)
