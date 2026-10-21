"""Real PG/Git/MCP/Docker progress journeys; explicit nonlive native/auth/capacity."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from test_native_plan_execution import native_plan as native_plan  # noqa: F401
from test_native_plan_execution import owner_cli as owner_cli  # noqa: F401
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401
from test_plan_revisions import fresh
from typer.testing import CliRunner

from panestria.cli.main import app
from panestria.kernel.build import BuildEvidenceService
from panestria.kernel.build_progress import BuildProgressService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.plan_returns import ReturnedBuildRelease
from panestria.kernel.plan_revisions import PlanRevisionService
from panestria.kernel.plan_store import PlanStore
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.uow import UnitOfWork


def inspect(owner, plan):
    with owner.connect() as c:
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        return BuildProgressService().inspect(
            UnitOfWork(c), owner.actor, plan.goal_id, BuildEvidenceService(owner.reports)
        )


@pytest.mark.parametrize("prepared_plan", [{"non_goals": ["No provider fallback or unrelated edits"]}], indirect=True)
def test_progress_tracks_real_candidate_and_merge_without_promoting_heartbeat_or_missing_bytes(native_plan, tmp_path):
    owner, runner, plan, _state = native_plan
    first = inspect(owner, plan)
    assert first.required_checks_passed == 0 and first.final_evidence_sha256 is None
    assert first.non_goals[0].status == "NOT_ASSESSED"
    assert first.attention_reason == "NO_VERIFIED_MILESTONE"
    with owner.connect() as c:
        append_event(
            UnitOfWork(c),
            goal_id=plan.goal_id,
            task_id=None,
            actor=owner.actor.owner_id,
            kind="worker.heartbeat",
            payload={"narrative": "Everything is done, all checks passed"},
        )
    activity = inspect(owner, plan)
    assert activity.as_of_event_seq > first.as_of_event_seq
    assert activity.required_checks_passed == 0 and activity.attention_reason == first.attention_reason
    assert runner.run(plan.plan_id, public_subscription_run=True)["status"] == "WAITING_APPROVAL"
    reviewed = inspect(owner, plan)
    assert reviewed.required_checks_passed == reviewed.required_checks_total > 0
    assert reviewed.goal_status == "ACTIVE" and reviewed.owner_merge == "PENDING"
    assert reviewed.release_acceptance == "NOT_ASSESSED" and reviewed.dispatch_authority == "NONE"
    current = reviewed.plans[-1]
    assert len(current.milestones) == 3 and sum(m.handoff_sha256 is not None for m in current.milestones) == 2
    with owner.connect() as c:
        before = c.execute("SELECT count(*) FROM panestria.task_event WHERE goal_id=%s", (plan.goal_id,)).fetchone()
    tmp_path.chmod(0o700)
    output = tmp_path / "progress.json"
    result = CliRunner().invoke(
        app,
        [
            "plan",
            "progress",
            owner.actor.owner_id,
            owner.actor.project_id,
            plan.goal_id,
            "--evidence-store",
            str(owner.reports.root),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    saved = json.loads(output.read_bytes())
    assert saved["final_evidence_sha256"] == reviewed.final_evidence_sha256
    assert "Final required checks [####################]" in result.output
    assert hashlib.sha256(output.read_bytes()).hexdigest() in result.output
    assert output.stat().st_mode & 0o077 == 0
    assert (
        CliRunner()
        .invoke(
            app,
            [
                "plan",
                "progress",
                owner.actor.owner_id,
                owner.actor.project_id,
                plan.goal_id,
                "--evidence-store",
                str(owner.reports.root),
                "--output",
                str(output),
            ],
        )
        .exit_code
        == 1
    )
    with owner.connect() as c:
        assert (
            c.execute("SELECT count(*) FROM panestria.task_event WHERE goal_id=%s", (plan.goal_id,)).fetchone()
            == before
        )
    view = owner.status(plan.goal_id)
    approval = view["approval"]
    owner.approve(
        approval["approval_id"], approval["effect_digest"], approval["expected_version"], "progress-test-owner"
    )
    completed = inspect(owner, plan)
    assert completed.attention_reason == "VERIFIED_BUILD_COMPLETED" and completed.owner_merge == "CONFIRMED"
    assert completed.release_acceptance == "NOT_ASSESSED"
    # An edited protected artifact cannot retain its prior progress score, even
    # though canonical task/goal completion still honestly records the past.
    blob = owner.reports.root / reviewed.final_evidence_sha256
    blob.chmod(0o600)
    blob.write_bytes(b'{"worker_narrative":"PASS"}')
    missing = inspect(owner, plan)
    assert missing.required_checks_passed == 0 and missing.final_evidence_sha256 is None
    assert missing.attention_reason == "COMPLETION_UNCONFIRMED"
    assert all(r.verdict == "UNCONFIRMED" for r in missing.requirements)


@pytest.mark.parametrize("prepared_plan", [{"wall_seconds": 900}], indirect=True)
def test_failed_final_check_is_visible_but_has_no_merge_authority_and_scope_is_checked(native_plan, tmp_path):
    owner, runner, plan, _state = native_plan
    script = owner.settings.root / "reviewed" / "required.py"
    script.write_text("raise AssertionError('synthetic final check fails')\n")
    check = owner.settings.checks[0].model_copy(update={"sha256": hashlib.sha256(script.read_bytes()).hexdigest()})
    owner.settings = owner.settings.model_copy(update={"checks": [check]})
    owner.registry = owner.settings.registry()
    assert runner.run(plan.plan_id, public_subscription_run=True)["status"] == "FAILED"
    progress = inspect(owner, plan)
    assert any(r.verdict == "FAIL" for r in progress.requirements)
    assert progress.required_checks_passed < progress.required_checks_total
    assert progress.attention_reason == "BUILD_STOPPED" and progress.owner_merge == "NOT_REQUESTED"
    final = progress.plans[-1].milestones[-1]
    assert final.evidence_status == "CONFIRMED" and final.failure_fingerprint
    assert progress.repair.repeated_failure_count == 1 and progress.repair.held_claims == 1
    # Repeating the same independently failed tree across a newly reviewed plan
    # is still a stall even when new task IDs/commit timestamps are assigned.
    with owner.connect() as c:
        attempt = c.execute(
            "SELECT attempt_id::text FROM panestria.build_active_worker_claim WHERE plan_id=%s", (plan.plan_id,)
        ).fetchone()[0]
        proof = ReturnedBuildRelease(owner.reports).release(UnitOfWork(c), owner.actor, plan.plan_id, attempt)
    with owner.connect() as c:
        parent = PlanStore().get(UnitOfWork(c), owner.actor, plan.plan_id)
        revised = PlanRevisionService().propose(
            UnitOfWork(c), owner.actor, plan.plan_id, plan.sha256(), fresh(plan), parent.inventory, proof
        )
    with owner.connect() as c:
        PlanStore().accept(
            UnitOfWork(c), owner.actor, revised.proposal.plan_id, revised.effect_digest, accept_plan=True
        )
    assert runner.run(revised.proposal.plan_id, public_subscription_run=True)["status"] == "FAILED"
    stalled = inspect(owner, plan)
    assert stalled.repair.repeated_failure_count == 2
    assert stalled.attention_reason == "REPEATED_UNCHANGED_FAILURE"
    assert stalled.repair.versions_used == 2 and stalled.repair.maximum_versions == 3
    assert stalled.repair.wall_envelope_charged_seconds == 540
    assert stalled.repair.wall_envelope_remaining_seconds == 360
    # The connected local repair controller must stop this actual unchanged
    # failed tree before consuming another model turn, even after physical return.
    from test_local_build_repair import local

    with owner.connect() as c:
        attempt = c.execute(
            "SELECT attempt_id::text FROM panestria.build_active_worker_claim WHERE plan_id=%s",
            (revised.proposal.plan_id,),
        ).fetchone()[0]
        current_proof = ReturnedBuildRelease(owner.reports).release(
            UnitOfWork(c), owner.actor, revised.proposal.plan_id, attempt
        )
    repair, model = local(owner, tmp_path)
    with pytest.raises(KernelDenied, match="local_repair_repeated_failure_owner_review_required"):
        repair.propose(
            revised.proposal.plan_id, revised.proposal.sha256(), current_proof,
            tmp_path / "stalled-repair", local_model_run=True,
        )
    assert not model.calls and not (tmp_path / "stalled-repair").exists()
    with owner.connect() as c:
        with pytest.raises(KernelDenied, match="stale_build_evidence"), c.transaction():
            BuildEvidenceService(owner.reports).current(
                UnitOfWork(c), owner.actor, final.task_id, final.evidence_sha256
            )
    with owner.connect() as c:
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        with pytest.raises(KernelDenied, match="not_found"):
            BuildProgressService().inspect(
                UnitOfWork(c),
                Actor(owner.actor.owner_id, str(uuid4())),
                plan.goal_id,
                BuildEvidenceService(owner.reports),
            )
    with owner.connect() as c:
        with pytest.raises(KernelDenied, match="progress_consistent_transaction_required"):
            BuildProgressService().inspect(
                UnitOfWork(c), owner.actor, plan.goal_id, BuildEvidenceService(owner.reports)
            )


def test_active_claimed_calls_are_activity_while_unknown_after_cancel_requires_reconciliation(native_plan):
    owner, runner, plan, state = native_plan
    state["block"] = True
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(runner.run, plan.plan_id, public_subscription_run=True)
        assert state["started"].wait(10)
        running = inspect(owner, plan)
        assert running.attention_reason == "EXECUTION_ACTIVE"
        assert running.required_checks_passed == 0 and running.repair.unconfirmed_invocations == 2
        assert running.repair.unknown_invocations == 0
        owner.cancel(plan.goal_id, owner.status(plan.goal_id)["row_version"])
        assert future.result(timeout=15)["status"] == "STOPPED"
    stopped = inspect(owner, plan)
    assert stopped.attention_reason == "RECONCILIATION_REQUIRED"
    assert stopped.repair.unknown_invocations >= 2 and stopped.repair.held_claims == 2
    assert stopped.required_checks_passed == 0
