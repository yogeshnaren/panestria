"""Actual queue/PG/Git/MCP/Docker boundaries; native/auth metadata are fixtures."""

import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_background_account import metadata
from test_background_queue import cli
from test_background_run import setup
from test_native_plan_execution import native_plan as native_plan  # noqa: F401
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401
from test_owner_build_cli import owner_cli as owner_cli  # noqa: F401
from test_registered_check_authority import git

from panestria.brokers.harness.account_profile import NativeAccountProbe
from panestria.brokers.harness.claude_build import ClaudeScopedBashAdapter
from panestria.execution import background_account as accounts
from panestria.execution.background_run import BackgroundPlanRunner


def no_acceptance(owner, plan, base):
    assert git(owner.settings.repository, "rev-parse", "refs/heads/main") == base
    with owner.connect() as c:
        for table, key in (("build_handoff", "plan_id"), ("approval_request", "goal_id")):
            # Constant, trusted table/key pairs; no owner/model SQL interpolation.
            value = plan.plan_id if key == "plan_id" else plan.goal_id
            assert c.execute(f"SELECT count(*) FROM panestria.{table} WHERE {key}=%s", (value,)).fetchone() == (0,)
        assert c.execute(
            "SELECT count(*) FROM panestria.build_evidence e JOIN panestria.task t ON t.id=e.task_id "
            "WHERE t.goal_id=%s",
            (plan.goal_id,),
        ).fetchone() == (0,)


def change_account(monkeypatch):
    transport = metadata(email="different-synthetic-owner@panestria.invalid")
    monkeypatch.setattr(accounts, "NativeAccountProbe", lambda a: NativeAccountProbe(a, runner=transport))


@pytest.mark.parametrize("change", ["withdraw", "account"])
def test_change_after_invocation_claim_stops_context_disclosure(prepared_plan, native_plan, monkeypatch, change):
    f, owner, plan, state, request, _ = setup(prepared_plan, native_plan, monkeypatch)
    native = ClaudeScopedBashAdapter.build_public
    changed = []

    def launch(adapter, session, **kwargs):
        before = kwargs["before_launch"]

        def change_before_launch():
            with owner.connect() as c:
                # This is after the durable native invocation, not merely before claim.
                assert c.execute(
                    "SELECT count(*) FROM panestria.worker_invocation i JOIN panestria.task t ON t.id=i.task_id "
                    "WHERE t.goal_id=%s AND i.state='CLAIMED'",
                    (plan.goal_id,),
                ).fetchone() == (1,)
            if change == "withdraw":
                cli(f, "withdraw", request.item_id, cli(f, "show", request.item_id)["binding_sha256"])
            else:
                change_account(monkeypatch)
            changed.append(change)
            before()

        return native(adapter, session, **{**kwargs, "before_launch": change_before_launch})

    monkeypatch.setattr(ClaudeScopedBashAdapter, "build_public", launch)
    result = BackgroundPlanRunner(owner, request.item_id).run_item(allow_background_subscription_run=True)
    assert changed == [change]  # The requested change actually reached the disclosure boundary.
    assert state["launches"] == 0
    assert result["status"] == "STOPPED", result
    with owner.connect() as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.task_event WHERE goal_id=%s AND kind='native_build.context_disclosure'",
            (plan.goal_id,),
        ).fetchone() == (0,)
    assert cli(f, "runs", request.item_id)["claims"][0]["capacity_held"] is True
    no_acceptance(owner, plan, f.base)


def test_withdrawal_interrupts_active_worker_and_retains_uncertain_claim(prepared_plan, native_plan, monkeypatch):
    f, owner, plan, state, request, _ = setup(prepared_plan, native_plan, monkeypatch)
    state["block"] = True
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            lambda: BackgroundPlanRunner(owner, request.item_id).run_item(allow_background_subscription_run=True)
        )
        deadline = time.monotonic() + 10
        while not state["active"] and not future.done() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert state["active"] == 1
        cli(f, "withdraw", request.item_id, cli(f, "show", request.item_id)["binding_sha256"])
        result = future.result(timeout=10)
    assert result["status"] == "STOPPED" and state["launches"] == 1
    assert result["worker_observations"][0]["status"] == "CANCELLED"
    assert cli(f, "runs", request.item_id)["claims"][0]["capacity_held"] is True
    no_acceptance(owner, plan, f.base)


def test_account_change_on_tool_return_cannot_publish_verified_result(prepared_plan, native_plan, monkeypatch):
    f, owner, plan, state, request, _ = setup(prepared_plan, native_plan, monkeypatch)
    native = ClaudeScopedBashAdapter.build_public

    def returned(adapter, session, **kwargs):
        outcome = native(adapter, session, **kwargs)  # Actual scoped tool edit and durable physical receipt.
        change_account(monkeypatch)
        return outcome

    monkeypatch.setattr(ClaudeScopedBashAdapter, "build_public", returned)
    result = BackgroundPlanRunner(owner, request.item_id).run_item(allow_background_subscription_run=True)
    assert result["status"] == "STOPPED" and state["launches"] == 1
    with owner.connect() as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.worker_invocation i JOIN panestria.task t ON t.id=i.task_id "
            "WHERE t.goal_id=%s AND i.binding->>'kind'='native-tool' AND i.state='RETURNED'",
            (plan.goal_id,),
        ).fetchone() == (1,)
    no_acceptance(owner, plan, f.base)
