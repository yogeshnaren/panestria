"""Actual PG authority rejects widening a historical closed-input permit."""

import time
from dataclasses import replace
from uuid import uuid4

import pytest
from test_registered_check_authority import configured as configured

from panestria.execution import registered_checks as checks
from panestria.execution.tool_authority import DurableToolAuthority, tool_binding
from panestria.kernel.invocations import InvocationService
from panestria.kernel.uow import UnitOfWork
from panestria.sandbox.native_tool_gateway import ToolPermit
from panestria.sandbox.runner import DockerSandbox, SandboxLaunchReference


def test_closed_permit_cannot_journal_a_framed_launch_even_with_matching_new_hash(configured, monkeypatch):
    task, args = configured
    controller = checks.RegisteredCheckController(*args)
    # Native gateway now requires framed mode. This independently exercises the
    # retained closed-profile authority contract without bypassing that guard.
    closed = replace(controller.profile, stdin_mode="closed")
    permit = ToolPermit(
        controller.scope,
        controller.request.sha256(),
        controller.registry.sha256(),
        controller.snapshot.directory,
        closed,
        time.monotonic() + 10,
    )
    binding = tool_binding(permit)
    with controller.connect() as connection:
        identity = InvocationService().prepare(UnitOfWork(connection), controller.actor, binding, "closed-mode-proof")
    authority = DurableToolAuthority(controller.connect, controller.actor, identity)
    authority.claim(permit)
    changed = replace(closed, stdin_mode="native-frame-v1")
    reference = SandboxLaunchReference(str(uuid4()), str(uuid4()), changed.sha256(), "sha256:" + "a" * 64)

    def forbidden(*args, **kwargs):
        raise AssertionError("no Docker operation permitted by this failed profile binding")

    monkeypatch.setattr(DockerSandbox, "_docker", forbidden)
    with pytest.raises(ValueError, match="sandbox_launch_profile_mismatch"):
        authority.record_launch(permit, reference, changed)
    with controller.connect() as connection:
        assert connection.execute(
            "SELECT state,receipt_sha256 FROM panestria.worker_invocation WHERE id=%s", (identity,)
        ).fetchone() == ("CLAIMED", None)
        assert connection.execute(
            "SELECT count(*) FROM panestria.worker_invocation_launch WHERE invocation_id=%s", (identity,)
        ).fetchone() == (0,)
