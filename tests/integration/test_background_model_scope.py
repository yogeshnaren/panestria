"""Actual canonical PG/Git/MCP/Docker; synthetic model/account/billing/certificates."""

import pytest
from test_background_queue import cli, record
from test_background_run import setup as background_setup
from test_native_connection_grants import setup as connection_setup
from test_native_plan_execution import native_plan as native_plan  # noqa: F401
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401
from test_owner_build_cli import owner_cli as owner_cli  # noqa: F401

from panestria.contracts.background import BackgroundEnqueue
from panestria.execution.background_run import BackgroundPlanRunner
from panestria.execution.build_plan import BuildIntegrator
from panestria.kernel.errors import KernelDenied


@pytest.mark.parametrize("owner_cli", [{"native_model": "claude-sonnet-5"}], indirect=True)
def test_selected_model_background_run_keeps_serial_workers_and_exact_final_review(
    prepared_plan, native_plan, monkeypatch
):
    f, owner, plan, state, request, view = background_setup(prepared_plan, native_plan, monkeypatch)
    connection_setup(native_plan, monkeypatch, observation_sha256=view["observation_sha256"])
    runner = BackgroundPlanRunner(owner, request.item_id)
    result = runner.run_item(allow_background_subscription_run=True)
    assert result["status"] == "WAITING_APPROVAL", result
    assert state["launches"] == 2 and state["peak"] == 1
    assert runner.run_record.model_ref == request.policy.model_ref == "claude-sonnet-5"
    run = cli(f, "runs", request.item_id)["runs"][0]["run"]
    assert run["schema_version"] == 2 and run["model_ref"] == "claude-sonnet-5"
    assert run["dispatch_authority"] == "NONE"


@pytest.mark.parametrize("owner_cli", [{"native_model": "claude-sonnet-5"}], indirect=True)
def test_exact_model_reserve_does_not_disappear_into_available_account_quota(prepared_plan, native_plan, monkeypatch):
    f, owner, plan, state, request, view = background_setup(prepared_plan, native_plan, monkeypatch)
    connection_setup(native_plan, monkeypatch, observation_sha256=view["observation_sha256"])
    model_scope = next(s for s in request.policy.quota_windows if s.model_ref is not None)
    record(owner, plan.nodes[-1].task_id, model_scope, remaining="10")
    inspected = cli(f, "show", request.item_id)
    assert "regular_use_reserve" in inspected["waiting_reasons"]
    assert inspected["requested_model"] == "claude-sonnet-5"
    assert any(o["model_ref"] is None and o["effective_remaining"] == "40" for o in inspected["quota_observations"])
    result = BackgroundPlanRunner(owner, request.item_id).run_item(allow_background_subscription_run=True)
    assert result["status"] == "WAIT" and state["launches"] == 0
    owner.settings = owner.settings.model_copy(update={"native_model": None})
    with pytest.raises(KernelDenied, match="background_requested_model_changed"):
        BackgroundPlanRunner(owner, request.item_id)._preflight(plan.plan_id)


@pytest.mark.parametrize("owner_cli", [{"native_model": "claude-sonnet-5"}], indirect=True)
def test_changed_model_after_worker_handoffs_fences_final_publication(prepared_plan, native_plan, monkeypatch):
    f, owner, plan, state, request, view = background_setup(prepared_plan, native_plan, monkeypatch)
    connection_setup(native_plan, monkeypatch, observation_sha256=view["observation_sha256"])
    original = BuildIntegrator._authorize
    reached = []

    def changed(controller):
        if not reached:
            reached.append(True)
            owner.settings = owner.settings.model_copy(update={"native_model": None})
        return original(controller)

    monkeypatch.setattr(BuildIntegrator, "_authorize", changed)
    result = BackgroundPlanRunner(owner, request.item_id).run_item(allow_background_subscription_run=True)
    assert result["status"] == "WAIT" and reached and state["launches"] == 2
    with owner.connect() as c:
        assert c.execute("SELECT count(*) FROM panestria.build_handoff").fetchone() == (2,)
        assert c.execute("SELECT count(*) FROM panestria.approval_request").fetchone() == (0,)


@pytest.mark.parametrize("owner_cli", [{"native_model": "claude-sonnet-5"}], indirect=True)
def test_draft_is_explicit_model_review_with_unknown_billing_and_no_dispatch(prepared_plan):
    from uuid import uuid4

    f, owner, runner, plan = prepared_plan
    path = f.config.parent / "selected-background.json"
    result = cli(f, "draft", plan.plan_id, str(uuid4()), "--output", str(path))
    request = BackgroundEnqueue.model_validate_json(path.read_bytes())
    assert result["status"] == "DRAFTED" and result["billing"] == "UNKNOWN"
    assert request.policy.schema_version == 2 and request.policy.model_ref == "claude-sonnet-5"
    assert len(request.policy.quota_windows) == 3 and request.policy.billing is None
    assert request.policy.allow_unknown_quota is False and f.transport.launches == 0
