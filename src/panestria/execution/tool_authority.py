"""Commit-before-dispatch authority for the native gateway's reviewed tools."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

import psycopg

from panestria.contracts.invocation import InvocationBinding
from panestria.kernel.goals import Actor
from panestria.kernel.invocations import InvocationService
from panestria.kernel.uow import UnitOfWork
from panestria.sandbox.native_tool_gateway import ToolPermit


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
