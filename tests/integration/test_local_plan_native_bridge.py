"""Actual local draft compiler→canonical review→MCP/Docker/final merge; explicit native fixture."""

import json
from uuid import uuid4

import pytest
from test_native_plan_execution import native_plan as native_plan  # noqa: F401
from test_native_plan_execution import owner_cli as owner_cli  # noqa: F401
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401

from panestria.contracts.goal import load_contract
from panestria.execution.local_plan import validate_draft
from panestria.kernel.errors import KernelDenied
from panestria.kernel.plan_store import PlanStore
from panestria.kernel.plan_submission import PlanSubmissionService
from panestria.kernel.uow import UnitOfWork


def staged_draft(owner, original, edits):
    with owner.connect() as c:
        body = c.execute(
            "SELECT c.body FROM panestria.build_plan p JOIN panestria.goal_contract c ON c.id=p.contract_id WHERE p.id=%s",
            (original.plan_id,),
        ).fetchone()[0]
        inventory = PlanStore().get(UnitOfWork(c), owner.actor, original.plan_id).inventory
    contract = load_contract({**body, "goal_id": str(uuid4())})
    proposal, _validated = validate_draft(json.dumps({"edits": edits}), owner.actor, contract, inventory)
    with owner.connect() as c:
        staged = PlanSubmissionService().stage(
            UnitOfWork(c),
            owner.actor,
            contract.model_dump(mode="json"),
            proposal,
            inventory,
            "compiled-" + proposal.plan_id,
        )
    return proposal, staged


def edit(name, paths, depends=()):
    return {
        "task_id": name,
        "worker_ref": "claude-public-bash",
        "capabilities": ["scoped-bash"],
        "paths": paths,
        "acceptance_keys": ["paths"],
        "depends_on": list(depends),
        "wall_seconds_per_attempt": 90,
    }


def test_single_edit_compiled_plan_requires_exact_acceptance_then_reaches_real_final_merge(native_plan):
    owner, runner, original, state = native_plan
    state["expected_workers"] = 1
    proposal, staged = staged_draft(owner, original, [edit("edit-both", ["calculator.py", "notes/build.txt"])])
    assert len(proposal.nodes) == 2
    with pytest.raises(KernelDenied, match="plan_not_accepted"):
        runner.run(proposal.plan_id, public_subscription_run=True)
    assert state["launches"] == 0
    with owner.connect() as c:
        PlanStore().accept(UnitOfWork(c), owner.actor, proposal.plan_id, staged.effect_digest, accept_plan=True)
    result = runner.run(proposal.plan_id, public_subscription_run=True)
    assert result["status"] == "WAITING_APPROVAL", result
    assert state["launches"] == state["peak"] == 1
    assert state["contexts"][0]["assignment"]["paths"] == ["calculator.py", "notes/build.txt"]
    view = owner.status(proposal.goal_id, diff=True)
    assert "+value = 43" in view["diff"] and "+bounded Bash build" in view["diff"]
    assert all(c["verdict"] == "PASS" for c in view["checks"])
    with owner.connect() as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.build_handoff WHERE plan_id=%s", (proposal.plan_id,)
        ).fetchone() == (1,)
        assert c.execute(
            "SELECT count(*) FROM panestria.worker_invocation i JOIN panestria.task t ON t.id=i.task_id "
            "WHERE t.goal_id=%s AND i.state='RETURNED'",
            (proposal.goal_id,),
        ).fetchone() == (3,)
    approval = view["approval"]
    owner.approve(
        approval["approval_id"], approval["effect_digest"], approval["expected_version"], "compiled-test-owner"
    )
    with owner.connect() as c:
        assert c.execute("SELECT status FROM panestria.goal WHERE id=%s", (proposal.goal_id,)).fetchone() == (
            "COMPLETED",
        )
        assert c.execute(
            "SELECT count(*) FROM panestria.build_active_worker_claim WHERE plan_id=%s", (proposal.plan_id,)
        ).fetchone() == (0,)


def test_dependent_local_edit_graph_still_refuses_without_claim_or_provider_dispatch(native_plan):
    owner, runner, original, state = native_plan
    proposal, staged = staged_draft(
        owner, original, [edit("calculator", ["calculator.py"]), edit("note", ["notes/build.txt"], ("calculator",))]
    )
    with owner.connect() as c:
        PlanStore().accept(UnitOfWork(c), owner.actor, proposal.plan_id, staged.effect_digest, accept_plan=True)
    with pytest.raises(KernelDenied, match="supported_bounded_fork_join_required"):
        runner.run(proposal.plan_id, public_subscription_run=True)
    assert state["launches"] == 0
    with owner.connect() as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.build_worker_claim WHERE plan_id=%s", (proposal.plan_id,)
        ).fetchone() == (0,)
