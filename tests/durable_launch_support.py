"""Synthetic same-PG invocation fixtures; fake image metadata is not OS evidence."""

from uuid import UUID, uuid4

import psycopg

from panestria.contracts.invocation import InvocationBinding
from panestria.contracts.native_tools import ToolScope
from panestria.contracts.sandbox_launch import SandboxLaunchIntent
from panestria.kernel.goals import Actor
from panestria.kernel.invocations import InvocationService
from panestria.kernel.leases import LeaseService
from panestria.kernel.uow import UnitOfWork


def prepared(task, *, ttl=120):
    actor = Actor(task["owner"], task["project"])
    with psycopg.connect(task["dsn"], connect_timeout=1) as c:
        lease = LeaseService().acquire(UnitOfWork(c), actor, task["task"], "durable-launch-fixture", 0, ttl_seconds=120)
    binding = InvocationBinding(
        scope=ToolScope(
            owner_id=UUID(actor.owner_id),
            project_id=UUID(actor.project_id),
            task_id=UUID(task["task"]),
            attempt_id=UUID(lease.attempt_id),
            lease_epoch=lease.epoch,
            contract_sha256="ab" * 32,
            policy_ref="test-policy-v1",
        ),
        kind="native-tool",
        request_sha256="cd" * 32,
        configuration_sha256="ef" * 32,
    )
    with psycopg.connect(task["dsn"], connect_timeout=1) as c:
        identity = InvocationService().prepare(UnitOfWork(c), actor, binding, "durable-fixture", ttl_seconds=ttl)
    with psycopg.connect(task["dsn"], connect_timeout=1) as c:
        InvocationService().claim(UnitOfWork(c), actor, binding, identity)
    intent = SandboxLaunchIntent(
        invocation_id=UUID(identity),
        binding_sha256=binding.sha256(),
        scope_sha256=binding.scope.sha256(),
        runtime_attempt_id=uuid4(),
        launch_id=uuid4(),
        profile_sha256="a" * 64,
        image_id="sha256:" + "f" * 64,
    )
    return actor, binding, identity, intent
