"""Actual same-Postgres goal fencing and release audit; no live process is invented."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

import psycopg
import pytest
from build_support import build as build  # noqa: F401
from plan_support import PATHS, accepted, claim
from plan_support import r1_task as r1_task  # noqa: F401

from panestria.contracts.goal import contract_sha256
from panestria.contracts.invocation import InvocationBinding
from panestria.contracts.native_tools import ToolScope
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.invocations import InvocationService
from panestria.kernel.leases import LeaseService
from panestria.kernel.plan_lifecycle import PlanLifecycle
from panestria.kernel.scheduler import Scheduled
from panestria.kernel.uow import UnitOfWork


def cancel(build, plan):
    with psycopg.connect(build.task["dsn"]) as c:
        return PlanLifecycle().cancel(UnitOfWork(c), build.actor, plan.plan_id, plan.sha256())


@pytest.mark.parametrize("build", [PATHS], indirect=True)
def test_plan_cancellation_rollback_then_concurrent_replay_fences_all_tasks_and_releases_only_no_dispatch(build):
    plan = accepted(build)
    attempts = [claim(build, plan), claim(build, plan)]
    assert all(isinstance(a, Scheduled) for a in attempts)
    with psycopg.connect(build.task["dsn"]) as c:
        with pytest.raises(KernelDenied, match="not_found"), c.transaction():
            PlanLifecycle().cancel(
                UnitOfWork(c), Actor(str(uuid4()), build.actor.project_id), plan.plan_id, plan.sha256()
            )
        with pytest.raises(KernelDenied, match="plan_review_changed"), c.transaction():
            PlanLifecycle().cancel(UnitOfWork(c), build.actor, plan.plan_id, "ff" * 32)
        receipt = PlanLifecycle().cancel(UnitOfWork(c), build.actor, plan.plan_id, plan.sha256())
        assert receipt.status == "CANCELLED" and receipt.held_claims == 0
        c.rollback()
        assert c.execute("SELECT count(*) FROM panestria.build_active_worker_claim").fetchone() == (2,)
        assert c.execute("SELECT status FROM panestria.goal WHERE id=%s", (plan.goal_id,)).fetchone() == ("ACTIVE",)
        assert c.execute("SELECT count(*) FROM panestria.build_claim_release").fetchone() == (0,)
    barrier = Barrier(2)

    def one():
        barrier.wait(timeout=5)
        return cancel(build, plan)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(one) for _ in range(2)]
        results = [f.result(timeout=10) for f in futures]
    assert results[0] == results[1]
    assert results[0].status == "CANCELLED" and results[0].held_claims == 0
    with psycopg.connect(build.task["dsn"]) as c:
        assert (
            c.execute("SELECT state FROM panestria.task WHERE goal_id=%s", (plan.goal_id,)).fetchall()
            == [("CANCELLED",)] * 4
        )
        assert c.execute("SELECT count(*) FROM panestria.task_event WHERE kind='build.plan.cancelled'").fetchone() == (
            1,
        )
        assert c.execute("SELECT reason FROM panestria.build_claim_release").fetchall() == [("NO_DISPATCH",)] * 2
        with pytest.raises(psycopg.Error), c.transaction():
            c.execute("DELETE FROM panestria.build_claim_release")
        for attempt in attempts:
            with pytest.raises(KernelDenied, match="stale_lease"), c.transaction():
                LeaseService().require_current(
                    UnitOfWork(c), build.actor, attempt.lease.attempt_id, attempt.lease.epoch
                )


@pytest.mark.parametrize("build", [PATHS], indirect=True)
def test_unknown_native_invocation_retains_its_capacity_while_other_tasks_are_fenced(build):
    plan = accepted(build)
    one, two = claim(build, plan), claim(build, plan)
    assert isinstance(one, Scheduled) and isinstance(two, Scheduled)
    binding = InvocationBinding(
        scope=ToolScope(
            owner_id=UUID(build.actor.owner_id),
            project_id=UUID(build.actor.project_id),
            task_id=UUID(one.lease.task_id),
            attempt_id=UUID(one.lease.attempt_id),
            lease_epoch=one.lease.epoch,
            contract_sha256=contract_sha256(build.contract),
            policy_ref=build.contract.autonomy_profile_ref,
        ),
        kind="native-proposal",
        request_sha256="ab" * 32,
        configuration_sha256="cd" * 32,
    )
    service = InvocationService()
    with psycopg.connect(build.task["dsn"]) as c:
        identity = service.prepare(UnitOfWork(c), build.actor, binding, "synthetic-uncertain-launch")
    with psycopg.connect(build.task["dsn"]) as c:
        service.claim(UnitOfWork(c), build.actor, binding, identity)
    with psycopg.connect(build.task["dsn"]) as c:
        service.finish(UnitOfWork(c), build.actor, binding, identity, None)
    # Revocation must not make withdrawing the old plan impossible.
    from panestria.kernel.policy import PolicyService

    policy_service = PolicyService(build.certificates)
    proposed = build.policy.model_copy(
        update={
            "version": 3,
            "autonomy": build.policy.autonomy.model_copy(
                update={
                    "version": 3,
                    "actions": {**build.policy.autonomy.actions, "read": "observe", "edit": "observe"},
                }
            ),
        }
    )
    with psycopg.connect(build.task["dsn"]) as c:
        review = policy_service.propose(UnitOfWork(c), build.actor, build.task["task"], proposed)
    with psycopg.connect(build.task["dsn"]) as c:
        policy_service.decide(UnitOfWork(c), build.actor, review.review_id, review.effect_digest, "approve")
    with psycopg.connect(build.task["dsn"]) as c:
        policy_service.apply(UnitOfWork(c), build.actor, review.review_id, review.effect_digest)
    receipt = cancel(build, plan)
    assert receipt.status == "CANCEL_REQUESTED" and receipt.held_claims == 1 and receipt.stopping_tasks == 1
    assert cancel(build, plan) == receipt
    with psycopg.connect(build.task["dsn"]) as c:
        assert c.execute("SELECT attempt_id::text FROM panestria.build_active_worker_claim").fetchall() == [
            (one.lease.attempt_id,)
        ]
        assert c.execute(
            "SELECT state,receipt_sha256 FROM panestria.worker_invocation WHERE id=%s", (identity,)
        ).fetchone() == ("UNKNOWN", None)
        assert c.execute("SELECT status FROM panestria.goal WHERE id=%s", (plan.goal_id,)).fetchone() == ("ACTIVE",)
        assert c.execute(
            "SELECT count(*) FROM panestria.task_event WHERE kind='build.plan.cancel_requested'"
        ).fetchone() == (1,)
