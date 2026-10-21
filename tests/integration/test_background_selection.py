"""Real queue/PG/Git/MCP/Docker, explicit native/account/capacity fixtures."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from test_background_queue import cli, record, request_for
from test_background_run import setup
from test_native_plan_execution import native_plan as native_plan  # noqa: F401
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401
from test_owner_build_cli import owner_cli as owner_cli  # noqa: F401
from test_registered_check_authority import git

from panestria.contracts.background import BackgroundEnqueue
from panestria.contracts.goal import contract_sha256, load_contract
from panestria.kernel.background import BackgroundWorkService
from panestria.kernel.plan_store import PlanStore
from panestria.kernel.plan_submission import PlanSubmissionService
from panestria.kernel.uow import UnitOfWork


def another(f, owner, plan, original, *, priority=3, resets_in=None, unknown=False):
    """A separately accepted fresh goal/policy; no edits to old immutable facts."""
    with owner.connect() as c:
        doc = c.execute("SELECT body FROM panestria.goal_contract WHERE goal_id=%s", (plan.goal_id,)).fetchone()[0]
        inventory = PlanStore().get(UnitOfWork(c), owner.actor, plan.plan_id).inventory
    doc["goal_id"] = str(uuid4())
    goal = load_contract(doc)
    ids = {n.task_id: str(uuid4()) for n in plan.nodes}
    proposal = plan.model_copy(
        update={
            "plan_id": str(uuid4()),
            "goal_id": goal.goal_id,
            "contract_sha256": contract_sha256(goal),
            "nodes": tuple(
                n.model_copy(update={"task_id": ids[n.task_id], "depends_on": tuple(ids[d] for d in n.depends_on)})
                for n in plan.nodes
            ),
        }
    )
    with owner.connect() as c:
        staged = PlanSubmissionService().stage(UnitOfWork(c), owner.actor, doc, proposal, inventory, str(uuid4()))
    with owner.connect() as c:
        PlanStore().accept(UnitOfWork(c), owner.actor, proposal.plan_id, staged.effect_digest, accept_plan=True)
    base = request_for(owner, proposal, allow_unknown_quota=unknown).model_dump(mode="json")
    base["value_priority"] = priority
    base["policy"]["billing"] = {
        **original.policy.billing.model_dump(mode="json"),
        "account_ref": base["policy"]["quota_windows"][0]["account_ref"],
    }
    request = BackgroundEnqueue.model_validate_json(json.dumps(base))
    with owner.connect() as c:
        BackgroundWorkService().enqueue(
            UnitOfWork(c), owner.actor, request, request.policy.sha256(), accept_background_policy=True
        )
    if not unknown:
        for window in request.policy.quota_windows:
            changes = {"remaining": "40"}
            if resets_in is not None:
                changes["resets_at"] = (datetime.now(UTC) + timedelta(seconds=resets_in)).isoformat()
            record(owner, proposal.nodes[-1].task_id, window, **changes)
    review = cli(f, "probe-account", request.item_id)
    cli(
        f, "link-account", request.item_id, review["observation_sha256"], review["link_sha256"], "--accept-account-link"
    )
    return request, proposal


def test_connected_selector_orders_reviewed_jobs_and_runs_only_one_without_implicit_resume(
    prepared_plan, native_plan, monkeypatch
):
    f, owner, plan, state, original, _ = setup(prepared_plan, native_plan, monkeypatch)
    later, _ = another(f, owner, plan, original, resets_in=2000)
    sooner, _ = another(f, owner, plan, original, resets_in=1800)
    unknown, _ = another(f, owner, plan, original, unknown=True)
    with owner.connect() as c:
        before = c.execute("SELECT count(*) FROM panestria.task_event").fetchone()
    preview = cli(f, "next")
    assert preview["selected"]["item_id"] == sooner.item_id and preview["candidate_count"] == 4
    assert preview["execution_authority"] == "NONE" and state["launches"] == 0
    with owner.connect() as c:
        assert c.execute("SELECT count(*) FROM panestria.task_event").fetchone() == before
    cli(f, "withdraw", sooner.item_id, preview["selected"]["binding_sha256"])
    assert cli(f, "next")["selected"]["item_id"] == later.item_id
    cli(f, "withdraw", later.item_id, cli(f, "show", later.item_id)["binding_sha256"])
    assert cli(f, "next")["selected"]["item_id"] == unknown.item_id
    cli(f, "withdraw", unknown.item_id, cli(f, "show", unknown.item_id)["binding_sha256"])
    assert cli(f, "next")["selected"]["item_id"] == original.item_id
    cli(f, "run-next", expected=1)
    assert state["launches"] == 0
    result = cli(f, "run-next", "--allow-background-subscription-run")
    assert result["status"] == "WAITING_APPROVAL" and result["selected_item_id"] == original.item_id
    assert state["launches"] == 2 and state["peak"] == 1
    assert git(f.bare, "rev-parse", "HEAD") == f.base  # Never auto-approve.
    assert owner.status(plan.goal_id)["task_state"] == "WAITING_APPROVAL"
    waiting = cli(f, "next")
    assert waiting["selected"] is None  # Pending final review still holds canonical capacity.
    assert waiting["skipped_reasons"]["started_job_requires_explicit_inspection_or_resume"] == 1


def test_connected_selection_rechecks_withdrawal_without_trying_another_job(prepared_plan, native_plan, monkeypatch):
    from panestria.execution import background_run

    f, owner, plan, state, original, _ = setup(prepared_plan, native_plan, monkeypatch)
    first, _ = another(f, owner, plan, original)
    read = background_run.select_next

    def withdraw_after_preview(owner):
        view = read(owner)
        selected = view["selected"]
        with owner.connect() as c:
            BackgroundWorkService().withdraw(
                UnitOfWork(c), owner.actor, selected["item_id"], selected["binding_sha256"]
            )
        return view

    monkeypatch.setattr(background_run, "select_next", withdraw_after_preview)
    result = background_run.run_next(owner, allow_background_subscription_run=True)
    assert result["status"] == "WAIT" and result["selected_item_id"] == first.item_id
    assert result["reason"] == "background_item_withdrawn" and state["launches"] == 0
    assert read(owner)["selected"]["item_id"] == original.item_id
    cli(f, "withdraw", original.item_id, cli(f, "show", original.item_id)["binding_sha256"])
    assert read(owner)["status"] == "WAIT" and read(owner)["selected"] is None
