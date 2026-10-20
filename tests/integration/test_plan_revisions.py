"""Actual canonical finite revision/execution; provider/auth/capacity are explicit fixtures."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from test_native_plan_execution import native_plan as native_plan  # noqa: F401
from test_native_plan_execution import owner_cli as owner_cli  # noqa: F401
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401

from panestria.contracts.plan import PlanProposal, PlanRevisionConsent
from panestria.kernel.errors import KernelDenied
from panestria.kernel.plan_lifecycle import PlanLifecycle
from panestria.kernel.plan_returns import ReturnedBuildRelease
from panestria.kernel.plan_revisions import PlanRevisionService
from panestria.kernel.plan_store import PlanStore
from panestria.kernel.scheduler import Scheduler
from panestria.kernel.uow import UnitOfWork


def fresh(plan):
    ids = {node.task_id: str(uuid4()) for node in plan.nodes}
    return PlanProposal.model_validate(
        {
            **plan.model_dump(),
            "plan_id": str(uuid4()),
            "nodes": tuple(
                node.model_copy(
                    update={"task_id": ids[node.task_id], "depends_on": tuple(ids[d] for d in node.depends_on)}
                )
                for node in plan.nodes
            ),
        }
    )


def failed(native_plan):
    owner, runner, plan, state = native_plan
    state["unavailable"] = True
    assert runner.run(plan.plan_id, public_subscription_run=True)["status"] == "STOPPED"
    with owner.connect() as c:
        parent = PlanStore().get(UnitOfWork(c), owner.actor, plan.plan_id)
        claims = [
            row[0]
            for row in c.execute(
                "SELECT attempt_id::text FROM panestria.build_active_worker_claim WHERE plan_id=%s",
                (plan.plan_id,),
            ).fetchall()
        ]
    return owner, runner, parent, state, claims


def returned(owner, parent, claims):
    result = None
    for attempt in claims:
        with owner.connect() as c:
            result = ReturnedBuildRelease(owner.reports).release(
                UnitOfWork(c), owner.actor, parent.proposal.plan_id, attempt
            )
    assert result is not None
    return result


def revise(owner, parent, proposal, proof):
    with owner.connect() as c:
        return PlanRevisionService().propose(
            UnitOfWork(c),
            owner.actor,
            parent.proposal.plan_id,
            parent.proposal.sha256(),
            proposal,
            parent.inventory,
            proof,
        )


@pytest.mark.parametrize("prepared_plan", [{"wall_seconds": 900}], indirect=True)
def test_finite_linear_versions_require_fresh_exact_review_and_execute_only_latest(native_plan):
    owner, runner, first, state, claims = failed(native_plan)
    original = first.model_dump_json()
    proof = returned(owner, first, claims)
    proposal2 = fresh(first.proposal)
    with ThreadPoolExecutor(max_workers=2) as pool:
        calls = [pool.submit(revise, owner, first, proposal2, proof) for _ in range(2)]
        second, replayed = [future.result(timeout=10) for future in calls]
    assert second == replayed and second.version == 2 and second.state == "PROPOSED"
    assert isinstance(second.consent, PlanRevisionConsent) and second.consent.cumulative_wall_seconds == 540
    assert second.consent.parent_sha256 == first.proposal.sha256()
    with owner.connect() as c:
        assert PlanStore().get(UnitOfWork(c), owner.actor, first.proposal.plan_id).model_dump_json() == original
        assert c.execute(
            "SELECT count(*) FROM panestria.build_plan_task WHERE plan_id=%s", (proposal2.plan_id,)
        ).fetchone() == (0,)
    third = revise(owner, second, fresh(first.proposal), proof)
    assert third.version == 3 and third.consent.cumulative_wall_seconds == 810
    with pytest.raises(KernelDenied, match="plan_repair_limit_exhausted"):
        revise(owner, third, fresh(first.proposal), proof)
    with owner.connect() as c:
        with pytest.raises(KernelDenied, match="plan_parent_superseded"), c.transaction():
            PlanStore().accept(
                UnitOfWork(c), owner.actor, second.proposal.plan_id, second.effect_digest, accept_plan=True
            )
        PlanStore().accept(UnitOfWork(c), owner.actor, third.proposal.plan_id, third.effect_digest, accept_plan=True)
    # Stale accepted snapshots can be read but cannot dispatch or cancel the new
    # accepted version. Fresh owner review must target the current plan digest.
    with owner.connect() as c:
        with pytest.raises(KernelDenied, match="plan_parent_superseded"), c.transaction():
            Scheduler().inspect(UnitOfWork(c), owner.actor, first.proposal.plan_id, runner.evidence)
        with pytest.raises(KernelDenied, match="plan_parent_superseded"), c.transaction():
            PlanLifecycle().cancel(UnitOfWork(c), owner.actor, first.proposal.plan_id, first.proposal.sha256())
    state["unavailable"] = False
    result = runner.run(third.proposal.plan_id, public_subscription_run=True)
    assert result["status"] == "WAITING_APPROVAL", result
    view = owner.status(first.proposal.goal_id)
    assert view["task_id"] == third.proposal.nodes[-1].task_id and view["task_state"] == "WAITING_APPROVAL"
    approval = view["approval"]
    merged = owner.approve(
        approval["approval_id"], approval["effect_digest"], approval["expected_version"], "revised-test-owner"
    )
    assert merged["task_state"] == "COMPLETED"
    with owner.connect() as c:
        assert c.execute("SELECT status FROM panestria.goal WHERE id=%s", (first.proposal.goal_id,)).fetchone() == (
            "COMPLETED",
        )
        assert (
            c.execute(
                "SELECT count(*) FROM panestria.task t JOIN panestria.build_plan_task pt ON pt.task_id=t.id "
                "WHERE pt.plan_id=%s AND t.state='FAILED'",
                (first.proposal.plan_id,),
            ).fetchone()[0]
            >= 1
        )
        assert PlanStore().get(UnitOfWork(c), owner.actor, first.proposal.plan_id).model_dump_json() == original


def test_revision_cannot_create_a_fresh_wall_budget_or_enlarge_scope(native_plan):
    owner, _runner, first, _state, claims = failed(native_plan)
    proof = returned(owner, first, claims)
    with pytest.raises(KernelDenied, match="plan_repair_budget_exhausted"):
        revise(owner, first, fresh(first.proposal), proof)
    bad = fresh(first.proposal).model_copy(update={"contract_sha256": "ef" * 32})
    with pytest.raises(KernelDenied, match="plan_scope_change_requires_new_authorization"):
        revise(owner, first, bad, proof)
    with owner.connect() as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.build_plan WHERE goal_id=%s", (first.proposal.goal_id,)
        ).fetchone() == (1,)


@pytest.mark.parametrize("prepared_plan", [{"wall_seconds": 900}], indirect=True)
def test_active_or_unknown_previous_work_cannot_be_repaired_by_relabeling(native_plan):
    owner, runner, first, _state, claims = failed(native_plan)
    assert len(claims) == 2
    proof = returned(owner, first, claims[:1])
    with pytest.raises(KernelDenied, match="plan_previous_work_unconfirmed"):
        revise(owner, first, fresh(first.proposal), proof)
    with owner.connect() as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.build_plan WHERE goal_id=%s", (first.proposal.goal_id,)
        ).fetchone() == (1,)
        assert c.execute(
            "SELECT count(*) FROM panestria.build_active_worker_claim WHERE plan_id=%s", (first.proposal.plan_id,)
        ).fetchone() == (1,)
