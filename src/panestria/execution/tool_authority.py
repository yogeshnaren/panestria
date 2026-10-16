"""Commit-before-dispatch authority for the native gateway's reviewed tools."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg

from panestria.contracts.invocation import InvocationBinding
from panestria.contracts.sandbox_launch import SandboxLaunchIntent, SandboxLaunchObservation
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.invocations import InvocationService
from panestria.kernel.sandbox_launches import SandboxLaunchService
from panestria.kernel.uow import UnitOfWork
from panestria.sandbox.native_tool_gateway import RunnerFactory, ToolPermit
from panestria.sandbox.profiles import SandboxProfile
from panestria.sandbox.runner import DockerSandbox, LaunchReconciliation, SandboxLaunchReference


def tool_binding(permit: ToolPermit) -> InvocationBinding:
    configuration = {
        "workspace": str(permit.workspace),
        "profile_sha256": permit.profile.sha256(),
        "registry_sha256": permit.registry_sha256,
    }
    digest = hashlib.sha256(json.dumps(configuration, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return InvocationBinding(
        scope=permit.scope, kind="native-tool", request_sha256=permit.request_sha256, configuration_sha256=digest
    )


class DurableToolAuthority:
    def __init__(self, connect: Callable[[], psycopg.Connection[Any]], actor: Actor, invocation_id: str) -> None:
        self.connect, self.actor, self.identity = connect, actor, invocation_id
        self.service = InvocationService()

    def claim(self, permit: ToolPermit) -> None:
        with self.connect() as c:
            c.execute("SET LOCAL statement_timeout='300ms'")
            self.service.claim(UnitOfWork(c), self.actor, tool_binding(permit), self.identity)
        # Connection context has committed the one-use claim before returning.

    def check(self, permit: ToolPermit) -> None:
        with self.connect() as c:
            c.execute("SET LOCAL statement_timeout='300ms'")
            self.service.check(UnitOfWork(c), self.actor, tool_binding(permit), self.identity)

    def _authorize_launch(self, connection: psycopg.Connection[Any], permit: ToolPermit) -> None:
        self.service.check(UnitOfWork(connection), self.actor, tool_binding(permit), self.identity)

    def record_launch(self, permit: ToolPermit, reference: SandboxLaunchReference, profile: SandboxProfile) -> None:
        reference.validate()
        binding = tool_binding(permit)
        # The gateway reduces wall time to the remaining absolute deadline.
        # Every other declared resource/permission/image/identity stays exact.
        if (
            type(profile) is not SandboxProfile
            or type(profile.wall_seconds) not in {int, float}
            or replace(profile, wall_seconds=permit.profile.wall_seconds) != permit.profile
            or not 0.1 <= profile.wall_seconds <= permit.profile.wall_seconds
            or reference.profile_sha256 != profile.sha256()
        ):
            raise ValueError("sandbox_launch_profile_mismatch")
        intent = SandboxLaunchIntent(
            invocation_id=UUID(self.identity),
            binding_sha256=binding.sha256(),
            scope_sha256=permit.scope.sha256(),
            runtime_attempt_id=UUID(reference.attempt_id),
            launch_id=UUID(reference.launch_id),
            profile_sha256=reference.profile_sha256,
            image_id=reference.image_id,
        )
        with self.connect() as connection:
            connection.execute("SET LOCAL statement_timeout='300ms'")
            self._authorize_launch(connection, permit)
            SandboxLaunchService().record(UnitOfWork(connection), self.actor, binding, self.identity, intent)
        # Only an acknowledged committed intent permits the later Docker create.

    def runner_factory(self, permit: ToolPermit) -> RunnerFactory:
        return lambda root, mounts: DockerSandbox(
            root,
            runtime_mounts=mounts,
            on_launch=lambda reference, profile: self.record_launch(permit, reference, profile),
            before_start=lambda: self.check(permit),
        )

    def reconcile_launch(self, permit: ToolPermit, workspace_root: Path) -> LaunchReconciliation:
        """Historical exact cleanup; never calls claim/check to start or renew work."""
        binding = tool_binding(permit)
        service = SandboxLaunchService()
        try:
            with self.connect() as connection:
                connection.execute("SET LOCAL statement_timeout='300ms'")
                intent = service.read(UnitOfWork(connection), self.actor, binding, self.identity)
        except psycopg.Error:
            raise KernelDenied("sandbox_launch_recovery_unavailable") from None
        reference = SandboxLaunchReference(
            str(intent.runtime_attempt_id), str(intent.launch_id), intent.profile_sha256, intent.image_id
        )
        observed = DockerSandbox(workspace_root).reconcile_launch(reference)
        observation = SandboxLaunchObservation.model_validate(
            {
                "intent_sha256": intent.sha256(),
                "status": observed.status,
                "container_id": observed.container_id,
                "reason": observed.reason,
            }
        )
        try:
            with self.connect() as connection:
                connection.execute("SET LOCAL statement_timeout='300ms'")
                service.observe(UnitOfWork(connection), self.actor, binding, self.identity, observation)
        except psycopg.Error:
            raise KernelDenied("sandbox_launch_observation_unconfirmed") from None
        return observed
