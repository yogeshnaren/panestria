"""Dispatch is committed once; expiry and a lost reply never permit a second launch."""

from __future__ import annotations

import hashlib
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest

from panestria.contracts.invocation import InvocationBinding
from panestria.contracts.native_tools import ToolRequest, ToolScope
from panestria.execution.tool_authority import DurableToolAuthority, tool_binding
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.invocations import InvocationService
from panestria.kernel.leases import LeaseService
from panestria.kernel.uow import UnitOfWork
from panestria.sandbox.native_tool_gateway import (
    GatewayRejected,
    NativeCommandRegistry,
    NativeToolGateway,
    ReviewedCommand,
    ToolPermit,
)
from panestria.sandbox.profiles import SandboxProfile


def binding(task: dict[str, str]) -> tuple[Actor, InvocationBinding]:
    actor = Actor(task["owner"], task["project"])
    with psycopg.connect(task["dsn"]) as c:
        lease = LeaseService().acquire(UnitOfWork(c), actor, task["task"], "invocation-test", 0, ttl_seconds=60)
    return actor, InvocationBinding(
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


def test_claim_race_commits_once_and_lost_reply_cannot_restart(r1_task: dict[str, str]) -> None:
    actor, request = binding(r1_task)
    service = InvocationService()
    with psycopg.connect(r1_task["dsn"]) as c:
        identity = service.prepare(UnitOfWork(c), actor, request, "candidate-edit")

    def claim() -> str:
        try:
            with psycopg.connect(r1_task["dsn"]) as c:
                service.claim(UnitOfWork(c), actor, request, identity)
            return "claimed"
        except KernelDenied as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: claim(), range(2))) == ["claimed", "invocation_not_dispatchable"]
    # A new service/connection observes the already-committed claim, even when
    # the original launcher died before returning its process receipt.
    with psycopg.connect(r1_task["dsn"]) as c:
        assert InvocationService().prepare(UnitOfWork(c), actor, request, "candidate-edit") == identity
        c.commit()
        with pytest.raises(KernelDenied, match="invocation_not_dispatchable"), c.transaction():
            InvocationService().claim(UnitOfWork(c), actor, request, identity)
        service.finish(UnitOfWork(c), actor, request, identity, None)
        c.commit()
        service.finish(UnitOfWork(c), actor, request, identity, None)
        with pytest.raises(KernelDenied, match="invocation_not_dispatchable"), c.transaction():
            service.claim(UnitOfWork(c), actor, request, identity)
        assert c.execute("SELECT state FROM panestria.worker_invocation WHERE id=%s", (identity,)).fetchone() == (
            "UNKNOWN",
        )


def test_claim_and_event_rollback_together(r1_task: dict[str, str]) -> None:
    actor, request = binding(r1_task)
    service = InvocationService()
    with psycopg.connect(r1_task["dsn"]) as c:
        identity = service.prepare(UnitOfWork(c), actor, request, "one")
        c.commit()
        service.claim(UnitOfWork(c), actor, request, identity)
        c.rollback()
        assert c.execute("SELECT state FROM panestria.worker_invocation WHERE id=%s", (identity,)).fetchone() == (
            "PREPARED",
        )
        assert c.execute(
            "SELECT count(*) FROM panestria.task_event WHERE task_id=%s AND kind='invocation.claimed'",
            (r1_task["task"],),
        ).fetchone() == (0,)
        service.claim(UnitOfWork(c), actor, request, identity)


@pytest.mark.parametrize(
    "change", ["owner", "project", "task", "attempt", "epoch", "contract", "policy", "request", "config"]
)
def test_scope_and_binding_drift_refuses_dispatch(r1_task: dict[str, str], change: str) -> None:
    actor, request = binding(r1_task)
    service = InvocationService()
    with psycopg.connect(r1_task["dsn"]) as c:
        identity = service.prepare(UnitOfWork(c), actor, request, "one")
    if change in {"request", "config"}:
        wrong = request.model_copy(
            update={"request_sha256" if change == "request" else "configuration_sha256": "aa" * 32}
        )
    else:
        field = {
            "owner": "owner_id",
            "project": "project_id",
            "task": "task_id",
            "attempt": "attempt_id",
            "epoch": "lease_epoch",
            "contract": "contract_sha256",
            "policy": "policy_ref",
        }[change]
        value = (
            uuid4()
            if field.endswith("_id")
            else 2
            if change == "epoch"
            else "aa" * 32
            if change == "contract"
            else "other"
        )
        wrong = request.model_copy(update={"scope": request.scope.model_copy(update={field: value})})
    with psycopg.connect(r1_task["dsn"]) as c:
        with pytest.raises(KernelDenied), c.transaction():
            service.claim(UnitOfWork(c), actor, wrong, identity)
        assert c.execute("SELECT state FROM panestria.worker_invocation WHERE id=%s", (identity,)).fetchone() == (
            "PREPARED",
        )


@pytest.mark.parametrize("change", ["expiry", "cancel", "epoch", "contract"])
def test_check_revokes_authority_but_preserves_historical_receipt(r1_task: dict[str, str], change: str) -> None:
    actor, request = binding(r1_task)
    service = InvocationService()
    with psycopg.connect(r1_task["dsn"]) as c:
        identity = service.prepare(UnitOfWork(c), actor, request, "one", ttl_seconds=1 if change == "expiry" else 120)
        c.commit()
        service.claim(UnitOfWork(c), actor, request, identity)
    if change == "expiry":
        time.sleep(1.1)
    else:
        with psycopg.connect(r1_task["dsn"]) as c:
            if change == "cancel":
                c.execute("UPDATE panestria.task SET state='CANCELLING' WHERE id=%s", (r1_task["task"],))
            elif change == "epoch":
                c.execute("UPDATE panestria.task SET lease_epoch=2 WHERE id=%s", (r1_task["task"],))
            else:
                updated = str(uuid4())
                c.execute(
                    "INSERT INTO panestria.goal_contract(id,goal_id,version,body,sha256)"
                    " SELECT %s,goal_id,2,body,%s FROM panestria.goal_contract WHERE id=%s",
                    (updated, "aa" * 32, r1_task["contract"]),
                )
                c.execute("UPDATE panestria.task SET contract_id=%s WHERE id=%s", (updated, r1_task["task"]))
    with psycopg.connect(r1_task["dsn"]) as c:
        with pytest.raises(KernelDenied), c.transaction():
            service.check(UnitOfWork(c), actor, request, identity)
        service.finish(UnitOfWork(c), actor, request, identity, "bb" * 32)
        c.commit()
        service.finish(UnitOfWork(c), actor, request, identity, "bb" * 32)
        with pytest.raises(KernelDenied, match="invocation_already_finished"), c.transaction():
            service.finish(UnitOfWork(c), actor, request, identity, "cc" * 32)


def test_invocation_binding_and_history_are_database_immutable(r1_task: dict[str, str]) -> None:
    actor, request = binding(r1_task)
    service = InvocationService()
    with psycopg.connect(r1_task["dsn"]) as c:
        identity = service.prepare(UnitOfWork(c), actor, request, "one")
        c.commit()
        with pytest.raises(KernelDenied, match="idempotency_conflict"), c.transaction():
            service.prepare(UnitOfWork(c), actor, request.model_copy(update={"request_sha256": "aa" * 32}), "one")
        for sql in (
            "UPDATE panestria.worker_invocation SET binding='{}' WHERE id=%s",
            "DELETE FROM panestria.worker_invocation WHERE id=%s",
        ):
            with pytest.raises(psycopg.Error, match="immutable"), c.transaction():
                c.execute(sql, (identity,))


@pytest.mark.live
def test_real_gateway_uses_durable_claim_and_refuses_replay(r1_task: dict[str, str], tmp_path: Path) -> None:
    actor, original = binding(r1_task)
    workspace = tmp_path / "attempts" / "one"
    workspace.mkdir(parents=True)
    script = tmp_path / "write.py"
    script.write_text("from pathlib import Path\nPath('/workspace/output.txt').write_text('verified candidate')\n")
    script.chmod(0o600)
    registry = NativeCommandRegistry(
        (ReviewedCommand("reviewed-edit", script, hashlib.sha256(script.read_bytes()).hexdigest(), "edit"),)
    )
    request = ToolRequest(request_id=uuid4(), command_ref="reviewed-edit", payload_json="{}")
    permit = ToolPermit(
        original.scope,
        request.sha256(),
        registry.sha256(),
        workspace,
        SandboxProfile(uid=os.getuid(), gid=os.getgid()),
        time.monotonic() + 15,
    )

    def connect() -> psycopg.Connection[tuple[object, ...]]:
        return psycopg.connect(r1_task["dsn"], connect_timeout=1)

    with connect() as c:
        identity = InvocationService().prepare(UnitOfWork(c), actor, tool_binding(permit), "apply")
    gateway = NativeToolGateway(workspace.parent, registry, DurableToolAuthority(connect, actor, identity))
    receipt = gateway.execute(request, permit)
    assert receipt.outcome == "completed" and (workspace / "output.txt").read_text() == "verified candidate"
    with pytest.raises(GatewayRejected, match="dispatch_claim_denied"):
        gateway.execute(request, permit)
    with connect() as c:
        InvocationService().finish(UnitOfWork(c), actor, tool_binding(permit), identity, "ab" * 32)
