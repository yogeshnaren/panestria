"""Separately opted-in real subscription journey; no transport/capacity fixtures."""

import json
import os
import shutil
from pathlib import Path

import pytest
from test_background_queue import cli, request_for
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401
from test_owner_build_cli import owner_cli as owner_cli  # noqa: F401
from test_registered_check_authority import git

from panestria.config_build import load_build_settings
from panestria.config_local import read_private
from panestria.contracts.background import BackgroundEnqueue
from panestria.execution.owner_build import OwnerBuild
from panestria.kernel.background import BackgroundWorkService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.uow import UnitOfWork


@pytest.mark.live
def test_actual_subscription_background_job_review_metrics_and_offline_capture(prepared_plan, record_property):
    # Do NOT call native_plan/setup: they are transport fixtures and setup
    # copies a synthetic binary. The actual owner binary/profile stay untouched.
    f, _, _, plan = prepared_plan
    assert f.actual
    report = json.loads(read_private(Path(os.environ["PANESTRIA_BACKGROUND_BILLING_REPORT"]), 4096))
    assert (
        report["source"] == "OWNER_REPORTED"
        and report["usage_credits_enabled"] is False
        and report["profile_directory"] == f.cfg["native_config"]
        and report["provider_verified"] is False
    )
    record_property("scope", "ACTUAL_CLAUDE_BACKGROUND_PUBLIC_SYNTHETIC_JOB_SCRIPTED_TEST_OWNER_NOT_G3")
    record_property("billing_source", "OWNER_REPORTED_DISABLED_NOT_PROVIDER_ATTESTED")
    record_property("billing_report_received_at", report["observed_at"])
    record_property("billing_source_question_item", report["source_question_item"])
    record_property("quota_precision", "UNKNOWN_EXPLICIT_BOUNDED_BEST_EFFORT_NO_FAKE40PERCENT")
    record_property("runtime_certificate_sha256", f.cfg["certificate_sha256"])
    f.cfg.update(record_runtime_metrics=True, capture_verified_results=True)
    f.config.write_text(json.dumps(f.cfg))  # Newly generated synthetic test config only.
    owner = OwnerBuild(load_build_settings(f.config), f.dsn)
    request = request_for(owner, plan, allow_unknown_quota=True)
    body = request.model_dump(mode="json")
    body["policy"]["billing"] = {
        "reported_by": owner.actor.owner_id,
        "account_ref": request.policy.quota_windows[0].account_ref,
        "observed_at": report["observed_at"],
        "fresh_for_seconds": report["fresh_for_seconds"],
        "usage_credits_enabled": False,
    }
    request = BackgroundEnqueue.model_validate_json(json.dumps(body))
    with owner.connect() as c:
        BackgroundWorkService().enqueue(
            UnitOfWork(c), owner.actor, request, request.policy.sha256(), accept_background_policy=True
        )
    review = cli(f, "probe-account", request.item_id)
    cli(
        f, "link-account", request.item_id, review["observation_sha256"], review["link_sha256"], "--accept-account-link"
    )
    result = cli(f, "run", request.item_id, "--allow-background-subscription-run")
    record_property("background_result", json.dumps(result, sort_keys=True))
    assert result["status"] == "WAITING_APPROVAL", result
    assert result["billing_provider_verified"] is False and result["metrics"]["status"] == "SAVED"
    before = owner.status(plan.goal_id, diff=True)
    assert git(f.bare, "rev-parse", "HEAD") == f.base
    assert all(check["verdict"] == "PASS" for check in before["checks"])
    assert "+value = 43" in before["diff"] and "+bounded Bash build" in before["diff"]
    approval = before["approval"]
    with pytest.raises(KernelDenied):
        owner.approve(approval["approval_id"], "ff" * 32, approval["expected_version"], "wrong-background-review")
    assert git(f.bare, "rev-parse", "HEAD") == f.base
    merged = owner.approve(
        approval["approval_id"], approval["effect_digest"], approval["expected_version"], "exact-background-test-owner"
    )
    assert merged["task_state"] == "COMPLETED" and merged["offline_reference"]["status"] == "SAVED"
    record_property("confirmed_merge_result", json.dumps(merged, sort_keys=True))
    assert git(f.bare, "rev-parse", "HEAD") == before["candidate_commit"]
    assert git(f.source, "rev-parse", "HEAD") == f.base
    with owner.connect() as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.build_active_worker_claim WHERE plan_id=%s", (plan.plan_id,)
        ).fetchone() == (0,)
        calls = c.execute(
            "SELECT i.id::text,i.binding->>'kind',i.state,i.receipt_sha256::text "
            "FROM panestria.worker_invocation i JOIN panestria.task t ON t.id=i.task_id "
            "WHERE t.goal_id=%s ORDER BY i.created_at,i.id",
            (plan.goal_id,),
        ).fetchall()
        assert (
            len(calls) == 5
            and sum(r[1] == "native-proposal" for r in calls) == 2
            and all(r[2] == "RETURNED" for r in calls)
        )
        record_property("actual_invocations", json.dumps(calls))
    # Preserve only this PUBLIC synthetic test's small evidence, not credentials,
    # model cache, certificates, owner checkout or other project material.
    artifact_dir = Path(os.environ["PANESTRIA_BACKGROUND_JOURNEY_ARTIFACTS"])
    artifact_dir.mkdir(mode=0o700, exist_ok=False)
    for name in ("reports", "account-observations", "offline-results", "metrics"):
        shutil.copytree(f.root / name, artifact_dir / name)
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "source_goal": plan.goal_id,
                "plan": plan.plan_id,
                "background": result,
                "confirmed_merge": merged,
                "human_owner_acceptance": "NOT_GRANTED",
                "billing_provider_verified": False,
                "quota_precision": "UNKNOWN",
            },
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )
    record_property("retained_synthetic_artifacts", str(artifact_dir))
