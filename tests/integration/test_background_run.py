"""Real DB/Git/MCP/Docker finite jobs; native/auth/host are explicit fixtures."""

import hashlib
import json
import shutil
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

from test_background_account import metadata
from test_background_queue import cli, record, request_for
from test_native_plan_execution import native_plan as native_plan  # noqa: F401
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401
from test_owner_build_cli import owner_cli as owner_cli  # noqa: F401
from test_registered_check_authority import git

from panestria.brokers.harness.account_profile import NativeAccountProbe
from panestria.contracts.ask import AskSubmission
from panestria.contracts.background import BackgroundEnqueue
from panestria.execution import background_account as account_controller
from panestria.execution.background_run import BackgroundPlanRunner
from panestria.kernel.ask import AskService
from panestria.kernel.background import BackgroundWorkService
from panestria.kernel.background_run import BACKGROUND_SESSION_LOCK, BackgroundRunService
from panestria.kernel.build import BuildEvidenceService
from panestria.kernel.uow import UnitOfWork


def setup(prepared_plan, native_plan, monkeypatch, *, billing=True):
    f, owner, _, plan = prepared_plan
    state = native_plan[3]
    state["expected_workers"] = 1
    request = request_for(owner, plan)
    if billing:
        request = BackgroundEnqueue.model_validate_json(
            json.dumps(
                {
                    **request.model_dump(mode="json"),
                    "policy": {
                        **request.policy.model_dump(mode="json"),
                        "billing": {
                            "reported_by": owner.actor.owner_id,
                            "account_ref": request.policy.quota_windows[0].account_ref,
                            "observed_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
                            "usage_credits_enabled": False,
                        },
                    },
                }
            )
        )
    with owner.connect() as c:
        BackgroundWorkService().enqueue(
            UnitOfWork(c), owner.actor, request, request.policy.sha256(), accept_background_policy=True
        )
    for window in request.policy.quota_windows:
        record(owner, plan.nodes[-1].task_id, window, remaining="40")
    binary = Path(f.cfg["native_binary"])
    shutil.copyfile(Path(sys.executable).resolve(), binary)
    binary.chmod(0o700)
    monkeypatch.setattr(account_controller, "PINNED_BINARY_SHA256", hashlib.sha256(binary.read_bytes()).hexdigest())
    transport = metadata()
    monkeypatch.setattr(account_controller, "NativeAccountProbe", lambda a: NativeAccountProbe(a, runner=transport))
    view = cli(f, "probe-account", request.item_id)
    cli(f, "link-account", request.item_id, view["observation_sha256"], view["link_sha256"], "--accept-account-link")
    return f, owner, plan, state, request, view


def test_actual_serial_background_job_preserves_foreground_slot_and_exact_final_owner_review(
    prepared_plan, native_plan, monkeypatch
):
    f, owner, plan, state, request, _ = setup(prepared_plan, native_plan, monkeypatch)
    cli(f, "run", request.item_id, expected=1)
    entered, proceed = threading.Event(), threading.Event()
    original = BackgroundPlanRunner._one

    def pause(self, plan, job):
        if not entered.is_set():
            entered.set()
            assert proceed.wait(10)
        return original(self, plan, job)

    monkeypatch.setattr(BackgroundPlanRunner, "_one", pause)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            lambda: BackgroundPlanRunner(owner, request.item_id).run_item(allow_background_subscription_run=True)
        )
        assert entered.wait(10)
        duplicate = cli(f, "run", request.item_id, "--allow-background-subscription-run")
        assert duplicate["status"] == "WAIT" and duplicate["reason"] == "background_controller_already_active"
        with owner.connect() as c:
            assert c.execute("SELECT count(*) FROM panestria.build_active_worker_claim").fetchone() == (1,)
        proceed.set()
        result = future.result(timeout=30)
    assert result["status"] == "WAITING_APPROVAL", result
    assert state["launches"] == 2 and state["peak"] == 1
    assert result["billing_provider_verified"] is False
    assert git(owner.settings.repository, "rev-parse", "refs/heads/main") == f.base
    review = owner.status(plan.goal_id, diff=True)
    assert review["task_state"] == "WAITING_APPROVAL" and all(v["verdict"] == "PASS" for v in review["checks"])
    history = cli(f, "runs", request.item_id)
    assert len(history["runs"]) == 1 and history["runs"][0]["coordinator_status"] == "RETURN_RECORDED"
    assert history["runs"][0]["claim_release_authority"] == "NONE"
    with owner.connect() as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.worker_invocation i JOIN panestria.task t ON t.id=i.task_id "
            "WHERE t.goal_id=%s AND i.state='RETURNED'",
            (plan.goal_id,),
        ).fetchone() == (5,)


def test_actual_foreground_ask_yields_new_background_claims_and_explicit_resume_reuses_handoff(
    prepared_plan, native_plan, monkeypatch
):
    from uuid import uuid4

    f, owner, plan, state, request, _ = setup(prepared_plan, native_plan, monkeypatch)
    ask_id = str(uuid4())
    original = BackgroundPlanRunner._one
    prepared = []

    def foreground(self, plan, job):
        result = original(self, plan, job)
        if not prepared:
            with owner.connect() as c:
                AskService().prepare(
                    UnitOfWork(c),
                    owner.actor,
                    AskSubmission(
                        request_id=ask_id,
                        project_id=owner.actor.project_id,
                        question="Synthetic foreground question",
                        privacy_label="PUBLIC",
                    ),
                )
            prepared.append(ask_id)
        return result

    monkeypatch.setattr(BackgroundPlanRunner, "_one", foreground)
    paused = cli(f, "run", request.item_id, "--allow-background-subscription-run")
    assert paused["status"] == "WAIT" and "foreground_or_held_capacity_reserved" in paused["background_wait_reason"]
    assert state["launches"] == 1 and state["peak"] == 1
    assert len(cli(f, "runs", request.item_id)["runs"]) == 1
    with owner.connect() as c:
        assert c.execute("SELECT count(*) FROM panestria.build_active_worker_claim").fetchone() == (0,)
        AskService().stop(
            UnitOfWork(c), owner.actor, ask_id, cancelled=True, code="synthetic_foreground_finished_no_inference"
        )
    resumed = cli(f, "run", request.item_id, "--allow-background-subscription-run")
    assert resumed["status"] == "WAITING_APPROVAL", resumed
    assert state["launches"] == 2  # Completed first worker was not re-run.
    assert len(cli(f, "runs", request.item_id)["runs"]) == 2
    assert git(owner.settings.repository, "rev-parse", "refs/heads/main") == f.base


def test_actual_coordinator_crash_reconciliation_and_native_limit_keep_unknown_claims(
    prepared_plan, native_plan, monkeypatch
):
    from uuid import uuid4

    f, owner, plan, state, request, view = setup(prepared_plan, native_plan, monkeypatch)
    reports = account_controller.account_reports(owner)
    service = BackgroundRunService(reports, BuildEvidenceService(owner.reports))
    with owner.connect() as guard:
        assert guard.execute("SELECT pg_try_advisory_lock(%s,%s)", BACKGROUND_SESSION_LOCK).fetchone() == (True,)
        guard.commit()
        with owner.connect() as c:
            crashed = service.start(
                UnitOfWork(c), owner.actor, request.item_id, view["observation_sha256"], str(uuid4())
            )
        cli(f, "reconcile-run", request.item_id, crashed.sha256(), expected=1)
    # Simulate only coordinator death before any claim: no process outcome is invented.
    waiting = cli(f, "run", request.item_id, "--allow-background-subscription-run")
    assert waiting["status"] == "WAIT" and "requires_reconciliation" in waiting["reason"]
    assert state["launches"] == 0
    cli(f, "reconcile-run", request.item_id, "ff" * 32, expected=1)
    assert cli(f, "reconcile-run", request.item_id, crashed.sha256())["claim_release_authority"] == "NONE"
    state["unavailable"] = True
    stopped = cli(f, "run", request.item_id, "--allow-background-subscription-run")
    assert stopped["status"] == "STOPPED" and state["launches"] == 1
    history = cli(f, "runs", request.item_id)
    assert history["claims"] and any(c["capacity_held"] for c in history["claims"])
    cli(f, "reconcile-run", request.item_id, stopped["background_run_sha256"], expected=1)
    again = cli(f, "run", request.item_id, "--allow-background-subscription-run")
    assert again["status"] == "WAIT" and state["launches"] == 1
    with owner.connect() as c:
        limited = c.execute(
            "SELECT payload FROM panestria.task_event WHERE goal_id=%s AND kind='background.route_limited'",
            (plan.goal_id,),
        ).fetchone()
        assert limited is not None and limited[0]["remaining"] is limited[0]["resets_at"] is None
        assert c.execute(
            "SELECT count(*) FROM panestria.approval_request WHERE goal_id=%s", (plan.goal_id,)
        ).fetchone() == (0,)


def test_actual_unconfirmed_billing_never_starts_a_background_job(prepared_plan, native_plan, monkeypatch):
    f, owner, plan, state, request, _ = setup(prepared_plan, native_plan, monkeypatch, billing=False)
    result = cli(f, "run", request.item_id, "--allow-background-subscription-run")
    assert result["status"] == "WAIT" and "no_extra_spend_boundary_unconfirmed" in result["reason"]
    assert state["launches"] == 0 and cli(f, "runs", request.item_id)["runs"] == []
    with owner.connect() as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.task_attempt a JOIN panestria.task t ON t.id=a.task_id WHERE t.goal_id=%s",
            (plan.goal_id,),
        ).fetchone() == (0,)
