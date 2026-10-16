"""Actual PostgreSQL ledger semantics, synthetic metadata, no container or inference."""

import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest

from durable_launch_support import prepared
from panestria.contracts.sandbox_launch import SandboxLaunchObservation
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.invocations import InvocationService
from panestria.kernel.leases import LeaseService
from panestria.kernel.sandbox_launches import SandboxLaunchService
from panestria.kernel.uow import UnitOfWork


def test_intent_and_event_rollback_together_and_committed_duplicate_never_permits_dispatch(r1_task):
    actor, binding, identity, intent = prepared(r1_task)
    service = SandboxLaunchService()
    with psycopg.connect(r1_task["dsn"]) as c:
        service.record(UnitOfWork(c), actor, binding, identity, intent)
        c.rollback()
        assert c.execute(
            "SELECT count(*) FROM panestria.worker_invocation_launch WHERE invocation_id=%s", (identity,)
        ).fetchone() == (0,)
        assert c.execute(
            "SELECT count(*) FROM panestria.task_event WHERE task_id=%s AND kind='sandbox.launch.recorded'",
            (r1_task["task"],),
        ).fetchone() == (0,)
        c.commit()
        service.record(UnitOfWork(c), actor, binding, identity, intent)
        c.commit()
        assert service.read(UnitOfWork(c), actor, binding, identity) == intent
        c.commit()
        with pytest.raises(KernelDenied, match="sandbox_launch_already_recorded"), c.transaction():
            service.record(UnitOfWork(c), actor, binding, identity, intent)
        assert c.execute("SELECT state FROM panestria.worker_invocation WHERE id=%s", (identity,)).fetchone() == (
            "CLAIMED",
        )


def test_actual_concurrent_recorders_have_one_commit_and_one_bounded_denial(r1_task):
    actor, binding, identity, intent = prepared(r1_task)

    def record():
        try:
            with psycopg.connect(r1_task["dsn"]) as c:
                SandboxLaunchService().record(UnitOfWork(c), actor, binding, identity, intent)
            return "committed"
        except KernelDenied as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: record(), range(2))) == ["committed", "sandbox_launch_already_recorded"]
    with psycopg.connect(r1_task["dsn"]) as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.task_event WHERE task_id=%s AND kind='sandbox.launch.recorded'",
            (r1_task["task"],),
        ).fetchone() == (1,)


@pytest.mark.parametrize("mutation", ["owner", "project", "binding", "scope", "invocation"])
def test_other_scope_or_binding_cannot_record_or_read_the_launch(r1_task, mutation):
    actor, binding, identity, intent = prepared(r1_task)
    service = SandboxLaunchService()
    with psycopg.connect(r1_task["dsn"]) as c:
        service.record(UnitOfWork(c), actor, binding, identity, intent)
    other_actor = actor
    if mutation == "owner":
        other_actor = Actor(str(uuid4()), actor.project_id)
    elif mutation == "project":
        other_actor = Actor(actor.owner_id, str(uuid4()))
    elif mutation == "binding":
        binding = binding.model_copy(update={"request_sha256": "e" * 64})
    elif mutation == "scope":
        binding = binding.model_copy(update={"scope": binding.scope.model_copy(update={"lease_epoch": 99})})
    else:
        identity = str(uuid4())
    with psycopg.connect(r1_task["dsn"]) as c:
        with pytest.raises(KernelDenied), c.transaction():
            service.read(UnitOfWork(c), other_actor, binding, identity)
        with pytest.raises(KernelDenied), c.transaction():
            service.record(UnitOfWork(c), other_actor, binding, identity, intent)


def test_actual_record_and_body_history_are_immutable_and_bare_autocommit_is_rejected(r1_task):
    actor, binding, identity, intent = prepared(r1_task)
    service = SandboxLaunchService()
    with psycopg.connect(r1_task["dsn"], autocommit=True) as c:
        with pytest.raises(KernelDenied, match="sandbox_launch_transaction_required"):
            service.record(UnitOfWork(c), actor, binding, identity, intent)
        with c.transaction():
            service.record(UnitOfWork(c), actor, binding, identity, intent)
        for sql in (
            "DELETE FROM panestria.worker_invocation_launch WHERE invocation_id=%s",
            "UPDATE panestria.worker_invocation_launch SET body='{}' WHERE invocation_id=%s",
        ):
            with pytest.raises(psycopg.Error, match="immutable"), c.transaction():
                c.execute(sql, (identity,))


@pytest.mark.parametrize("change", ["lease", "expiry"])
def test_revocation_or_expiry_does_not_hide_history_or_restore_execution_authority(r1_task, change):
    actor, binding, identity, intent = prepared(r1_task, ttl=1 if change == "expiry" else 120)
    service = SandboxLaunchService()
    with psycopg.connect(r1_task["dsn"]) as c:
        service.record(UnitOfWork(c), actor, binding, identity, intent)
    if change == "expiry":
        time.sleep(1.1)
    else:
        with psycopg.connect(r1_task["dsn"]) as c:
            LeaseService().release(UnitOfWork(c), actor, str(binding.scope.attempt_id), binding.scope.lease_epoch)
    with psycopg.connect(r1_task["dsn"]) as c:
        assert service.read(UnitOfWork(c), actor, binding, identity) == intent
        c.commit()
        with pytest.raises(KernelDenied), c.transaction():
            InvocationService().check(UnitOfWork(c), actor, binding, identity)
        service.observe(
            UnitOfWork(c),
            actor,
            binding,
            identity,
            SandboxLaunchObservation(
                intent_sha256=intent.sha256(), status="NOT_OBSERVED", reason="no_owned_container_observed"
            ),
        )
        c.commit()
        assert c.execute(
            "SELECT state,receipt_sha256 FROM panestria.worker_invocation WHERE id=%s", (identity,)
        ).fetchone() == ("UNKNOWN", None)
        with pytest.raises(KernelDenied), c.transaction():
            InvocationService().claim(UnitOfWork(c), actor, binding, identity)


def test_cleanup_observation_rollback_keeps_invocation_and_events_consistent(r1_task):
    actor, binding, identity, intent = prepared(r1_task)
    service = SandboxLaunchService()
    with psycopg.connect(r1_task["dsn"]) as c:
        service.record(UnitOfWork(c), actor, binding, identity, intent)
    with psycopg.connect(r1_task["dsn"]) as c:
        service.observe(
            UnitOfWork(c),
            actor,
            binding,
            identity,
            SandboxLaunchObservation(
                intent_sha256=intent.sha256(), status="UNCONFIRMED", reason="launch_runtime_unconfirmed"
            ),
        )
        c.rollback()
        assert c.execute("SELECT state FROM panestria.worker_invocation WHERE id=%s", (identity,)).fetchone() == (
            "CLAIMED",
        )
        assert c.execute(
            "SELECT count(*) FROM panestria.task_event WHERE task_id=%s AND kind='sandbox.launch.reconciled'",
            (r1_task["task"],),
        ).fetchone() == (0,)
