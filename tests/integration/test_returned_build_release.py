"""Actual PG/Git/Docker return release; native/auth/capacity are explicit fixtures."""

import hashlib
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from test_native_plan_execution import native_plan as native_plan  # noqa: F401
from test_native_plan_execution import owner_cli as owner_cli  # noqa: F401
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401

from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.plan_lifecycle import PlanLifecycle
from panestria.kernel.plan_returns import ReturnedBuildRelease
from panestria.kernel.uow import UnitOfWork


def attempts(owner, plan):
    with owner.connect() as c:
        return [
            row[0]
            for row in c.execute(
                "SELECT attempt_id::text FROM panestria.build_active_worker_claim WHERE plan_id=%s ORDER BY attempt_id",
                (plan.plan_id,),
            ).fetchall()
        ]


def release(owner, plan, attempt):
    with owner.connect() as c:
        return ReturnedBuildRelease(owner.reports).release(UnitOfWork(c), owner.actor, plan.plan_id, attempt)


def test_confirmed_native_rejections_release_once_without_retry_and_preserve_audit(native_plan):
    owner, runner, plan, state = native_plan
    state["unavailable"] = True
    outcome = runner.run(plan.plan_id, public_subscription_run=True)
    assert outcome["status"] == "STOPPED"
    claims = attempts(owner, plan)
    assert claims
    before_calls = state["launches"]
    # Releasing old physical work must not require renewing a revoked grant.
    from panestria.kernel.policy import PolicyService

    service = PolicyService(owner.certificates)
    with owner.connect() as c:
        current = service.get(UnitOfWork(c), owner.actor)
        changed = current.model_copy(
            update={
                "version": current.version + 1,
                "autonomy": current.autonomy.model_copy(
                    update={
                        "version": current.autonomy.version + 1,
                        "actions": {**current.autonomy.actions, "read": "observe", "edit": "observe"},
                    }
                ),
            }
        )
        review = service.propose(UnitOfWork(c), owner.actor, plan.nodes[-1].task_id, changed)
    with owner.connect() as c:
        service.decide(UnitOfWork(c), owner.actor, review.review_id, review.effect_digest, "approve")
    with owner.connect() as c:
        service.apply(UnitOfWork(c), owner.actor, review.review_id, review.effect_digest)
    with owner.connect() as c:
        with pytest.raises(KernelDenied, match="not_found"), c.transaction():
            ReturnedBuildRelease(owner.reports).release(
                UnitOfWork(c), Actor(str(uuid4()), owner.actor.project_id), plan.plan_id, claims[0]
            )
    for attempt in claims:
        with ThreadPoolExecutor(max_workers=2) as pool:
            one, two = [pool.submit(release, owner, plan, attempt) for _ in range(2)]
            assert one.result(timeout=10) == two.result(timeout=10)
    assert state["launches"] == before_calls and attempts(owner, plan) == []
    with owner.connect() as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.build_claim_release WHERE reason='VERIFIED_RETURN'"
        ).fetchone() == (len(claims),)
        assert c.execute(
            "SELECT count(*) FROM panestria.build_worker_claim WHERE plan_id=%s AND released_at IS NULL",
            (plan.plan_id,),
        ).fetchone() == (len(claims),)
        assert c.execute(
            "SELECT count(*) FROM panestria.approval_request WHERE goal_id=%s", (plan.goal_id,)
        ).fetchone() == (0,)
        with pytest.raises(psycopg.Error), c.transaction():
            c.execute("DELETE FROM panestria.build_claim_release WHERE attempt_id=%s", (claims[0],))
        stopped = PlanLifecycle().cancel(UnitOfWork(c), owner.actor, plan.plan_id, plan.sha256())
        assert stopped.status == "CANCELLED" and stopped.held_claims == 0
    refused = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "migrations/alembic.ini", "downgrade", "0035_build_claim_release"],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PANESTRIA_DATABASE_URL": owner.dsn},
        capture_output=True,
        timeout=30,
    )
    assert refused.returncode and b"returned Build release audit exists" in refused.stderr


def test_unknown_cancelled_native_work_stays_held_and_is_never_reclassified(native_plan):
    owner, runner, plan, state = native_plan
    state["block"] = True
    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(runner.run, plan.plan_id, public_subscription_run=True)
        assert state["started"].wait(10)
        with owner.connect() as c:
            PlanLifecycle().cancel(UnitOfWork(c), owner.actor, plan.plan_id, plan.sha256())
        assert running.result(timeout=15)["status"] == "STOPPED"
    claims = attempts(owner, plan)
    assert len(claims) == 2
    for attempt in claims:
        with pytest.raises(KernelDenied, match="build_return_invocations_unconfirmed"):
            release(owner, plan, attempt)
    assert attempts(owner, plan) == claims
    with owner.connect() as c:
        assert c.execute("SELECT count(*) FROM panestria.build_claim_release").fetchone() == (0,)
        assert c.execute("SELECT count(*) FROM panestria.worker_invocation WHERE state='UNKNOWN'").fetchone()[0] >= 2


@pytest.mark.parametrize("withdraw_after_pass", [False, True])
def test_final_return_release_preserves_failed_or_withdrawn_review_without_granting_merge(
    native_plan, withdraw_after_pass
):
    owner, runner, plan, state = native_plan
    if not withdraw_after_pass:
        script = owner.settings.root / "reviewed" / "required.py"
        script.write_text("raise AssertionError('synthetic combined check fails')\n")
        check = owner.settings.checks[0].model_copy(update={"sha256": hashlib.sha256(script.read_bytes()).hexdigest()})
        owner.settings = owner.settings.model_copy(update={"checks": [check]})
        owner.registry = owner.settings.registry()  # Explicit reviewed test-owner check before any dispatch.
    outcome = runner.run(plan.plan_id, public_subscription_run=True)
    assert outcome["status"] == ("WAITING_APPROVAL" if withdraw_after_pass else "FAILED"), outcome
    claims = attempts(owner, plan)
    assert len(claims) == 1
    if withdraw_after_pass:
        with owner.connect() as c:
            stopped = PlanLifecycle().cancel(UnitOfWork(c), owner.actor, plan.plan_id, plan.sha256())
            assert stopped.status == "CANCEL_REQUESTED" and stopped.held_claims == 1
    proof = release(owner, plan, claims[0])
    assert proof == release(owner, plan, claims[0]) and not attempts(owner, plan)
    with owner.connect() as c:
        assert c.execute("SELECT state FROM panestria.task WHERE id=%s", (plan.nodes[-1].task_id,)).fetchone() == (
            "CANCELLED" if withdraw_after_pass else "FAILED",
        )
        assert c.execute(
            "SELECT count(*) FROM panestria.side_effect WHERE task_id=%s AND state!='PREPARED'",
            (plan.nodes[-1].task_id,),
        ).fetchone() == (0,)
    assert state["launches"] == 2
