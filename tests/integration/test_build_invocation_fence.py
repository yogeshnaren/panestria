"""A passing candidate cannot hide an unfinished or unknown worker invocation."""

from uuid import UUID

import psycopg
import pytest
from build_support import BuildFixture, _publish
from build_support import build as build

from panestria.contracts.goal import contract_sha256
from panestria.contracts.invocation import InvocationBinding
from panestria.contracts.native_tools import ToolScope
from panestria.kernel.errors import KernelDenied
from panestria.kernel.invocations import InvocationService
from panestria.kernel.uow import UnitOfWork


@pytest.mark.parametrize("state", ["PREPARED", "CLAIMED", "UNKNOWN", "RETURNED"])
def test_build_waits_for_every_invocation_receipt(build: BuildFixture, state: str) -> None:
    binding = InvocationBinding(
        scope=ToolScope(
            owner_id=UUID(build.actor.owner_id),
            project_id=UUID(build.actor.project_id),
            task_id=UUID(build.task["task"]),
            attempt_id=UUID(build.attempt),
            lease_epoch=1,
            contract_sha256=contract_sha256(build.contract),
            policy_ref=build.contract.autonomy_profile_ref,
        ),
        kind="native-tool",
        request_sha256="ab" * 32,
        configuration_sha256="cd" * 32,
    )
    service = InvocationService()
    with psycopg.connect(build.task["dsn"]) as c:
        invocation = service.prepare(UnitOfWork(c), build.actor, binding, "edit")
        c.commit()
        if state != "PREPARED":
            service.claim(UnitOfWork(c), build.actor, binding, invocation)
            c.commit()
        if state in {"UNKNOWN", "RETURNED"}:
            service.finish(UnitOfWork(c), build.actor, binding, invocation, "ef" * 32 if state == "RETURNED" else None)
    if state == "RETURNED":
        assert _publish(build)
    else:
        with pytest.raises(KernelDenied, match="invocations_unconfirmed"):
            _publish(build)
