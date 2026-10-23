"""Actual final PG/Git/check receipts; native/auth/resource identities are fixtures."""

import pytest
from test_background_queue import cli
from test_background_run import setup
from test_native_plan_execution import native_plan as native_plan  # noqa: F401
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401
from test_owner_build_cli import owner_cli as owner_cli  # noqa: F401
from test_registered_check_authority import git

from panestria.execution import build_plan
from panestria.execution.background_run import BackgroundPlanRunner
from panestria.execution.build_plan import BuildIntegrator


@pytest.mark.parametrize("boundary", ["claimed", "returned"])
def test_withdrawn_final_claim_or_confirmed_checks_cannot_publish_approval(
    prepared_plan, native_plan, monkeypatch, boundary
):
    f, owner, plan, state, request, _ = setup(prepared_plan, native_plan, monkeypatch)
    final_task = plan.nodes[-1].task_id
    reached = []

    def withdraw():
        with owner.connect() as c:
            assert c.execute(
                "SELECT count(*) FROM panestria.build_active_worker_claim WHERE task_id=%s", (final_task,)
            ).fetchone() == (1,)
        cli(f, "withdraw", request.item_id, cli(f, "show", request.item_id)["binding_sha256"])
        reached.append(boundary)

    integrate = BuildIntegrator.verify_for_review

    def before(integrator, *args, **kwargs):
        if boundary == "claimed":
            withdraw()
        return integrate(integrator, *args, **kwargs)

    verify = build_plan.verify_build

    def returned(*args, **kwargs):
        checked = verify(*args, **kwargs)
        assert checked.bundle.task_id == final_task and checked.bundle.passed()
        withdraw()  # All actual checks have returned; this is not a mocked PASS.
        return checked

    monkeypatch.setattr(BuildIntegrator, "verify_for_review", before)
    if boundary == "returned":
        monkeypatch.setattr(build_plan, "verify_build", returned)
    result = BackgroundPlanRunner(owner, request.item_id).run_item(allow_background_subscription_run=True)
    assert reached == [boundary] and state["launches"] == 2
    assert result["status"] == "WAIT" and result["reason"] == "background_item_withdrawn", result
    assert git(owner.settings.repository, "rev-parse", "refs/heads/main") == f.base
    with owner.connect() as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.build_handoff WHERE plan_id=%s", (plan.plan_id,)
        ).fetchone() == (2,)
        assert c.execute(
            "SELECT count(*) FROM panestria.build_evidence WHERE task_id=%s", (final_task,)
        ).fetchone() == (0,)
        assert c.execute(
            "SELECT count(*) FROM panestria.approval_request WHERE goal_id=%s", (plan.goal_id,)
        ).fetchone() == (0,)
        invocations = c.execute(
            "SELECT state,receipt_sha256 FROM panestria.worker_invocation "
            "WHERE task_id=%s AND binding->>'kind'='build-integration'",
            (final_task,),
        ).fetchall()
        if boundary == "claimed":
            assert invocations == []
        else:
            assert len(invocations) == 1 and invocations[0][0] == "RETURNED" and invocations[0][1] is not None
        assert c.execute(
            "SELECT count(*) FROM panestria.build_active_worker_claim WHERE task_id=%s", (final_task,)
        ).fetchone() == (1,)  # Neither withdrawal nor a historical return is claim release.
