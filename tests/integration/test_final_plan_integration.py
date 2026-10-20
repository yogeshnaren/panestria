"""Actual completed sibling results, conflict detection and full Docker verification.

Workers/capacity are controller fixtures, not native vendor/OS qualification.
"""

import hashlib
import json
import time
from uuid import uuid4

import psycopg
import pytest
from build_support import _git
from build_support import build as build  # noqa: F401
from plan_support import PATHS, accepted, claim, verified_handoff
from plan_support import r1_task as r1_task  # noqa: F401

from panestria.execution.build_plan import BuildIntegrator
from panestria.kernel.errors import KernelDenied
from panestria.kernel.scheduler import Scheduled, Scheduler
from panestria.kernel.uow import UnitOfWork
from panestria.verification.git_snapshot import SnapshotRejected, materialize


def owner_review(build, tmp_path):
    """Actual private Build settings, reviewed script, CAS and merge target; no native call."""
    from panestria.config_build import BuildSettings
    from panestria.execution.owner_build import OwnerBuild
    from panestria.kernel.build import BuildEvidenceService

    reviewed = tmp_path / "reviewed"
    reviewed.mkdir(mode=0o700)
    script = reviewed / "required_check.py"
    script.write_bytes((build.registry.bundle_root / "required_check.py").read_bytes())
    script.chmod(0o600)
    settings = BuildSettings.model_validate_json(
        json.dumps(
            {
                "schema_version": 1,
                "owner_id": build.actor.owner_id,
                "project_id": build.actor.project_id,
                "root": str(tmp_path),
                "certificates": str(tmp_path / "unused-synthetic-certificates"),
                "certificate_sha256": "ab" * 32,
                "native_binary": str(tmp_path / "native-not-run"),
                "native_config": str(tmp_path / "auth-not-used"),
                "skills_archive": str(tmp_path / "probe-not-run"),
                "checks": [
                    {
                        "ref": "synthetic-test-suite",
                        "script": script.name,
                        "sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
                    }
                ],
            }
        )
    )
    owner = OwnerBuild(settings, build.task["dsn"])
    build.service = BuildEvidenceService(owner.reports)
    build.registry = owner.registry
    return owner


def connected(build):
    return lambda: psycopg.connect(build.task["dsn"], options="-c statement_timeout=3000 -c lock_timeout=1000")


def sibling(build, plan, scheduled, candidate, directory):
    receipt = verified_handoff(build, plan, scheduled, candidate, directory)
    assert receipt is not None
    with connected(build)() as c:
        Scheduler().complete_node(
            UnitOfWork(c), build.actor, plan.plan_id, receipt.submission.handoff_id, build.service
        )


def second_candidate(build, name, content):
    _git(build.source, "checkout", "-b", "worker-two", build.base)
    (build.source / name).write_text(content)
    _git(build.source, "add", name)
    _git(build.source, "commit", "-m", "synthetic second worker")
    candidate = _git(build.source, "rev-parse", "HEAD")
    _git(build.bare, "fetch", str(build.source), "worker-two")
    return candidate


@pytest.mark.parametrize("build", [PATHS], indirect=True)
@pytest.mark.parametrize("wrong_combined_output", [False, True])
def test_two_verified_siblings_require_full_exact_combined_checks_before_owner_review(
    build, tmp_path, wrong_combined_output
):
    # Reviewer-owned command is fixed before any worker verification/dispatch.
    (build.registry.bundle_root / "required_check.py").write_text(
        "import os\nfrom pathlib import Path\nr=Path(os.environ['PANESTRIA_CANDIDATE'])\n"
        "assert (r/'answer.txt').read_text()=='verified'\n"
        "assert (r/'part1.txt').read_text()=='second worker'\n"
    )
    from panestria.verification.registry import CommandRegistry

    build.registry = CommandRegistry.load(build.registry.bundle_root, "/synthetic/reviewed-python")
    owner = owner_review(build, tmp_path)
    with pytest.raises(SnapshotRejected, match="git_timeout"):
        materialize(build.bare, build.base, build.base, tmp_path / "expired-input", deadline=time.monotonic() - 1)
    assert not (tmp_path / "expired-input").exists()
    plan = accepted(
        build, base_snapshot_sha=materialize(build.bare, build.base, build.base, tmp_path / "inventory").manifest_sha256
    )
    one, two = claim(build, plan), claim(build, plan)
    assert isinstance(one, Scheduled) and isinstance(two, Scheduled)
    sibling(build, plan, one, build.candidate, tmp_path / "verified-one")
    candidate2 = second_candidate(build, "part1.txt", "wrong output" if wrong_combined_output else "second worker")
    sibling(build, plan, two, candidate2, tmp_path / "verified-two")
    final = claim(build, plan)
    assert isinstance(final, Scheduled)
    integrator = BuildIntegrator(connected(build), build.actor, build.service, build.certificates)
    result = integrator.verify_for_review(
        plan.plan_id,
        final.lease.attempt_id,
        final.lease.epoch,
        build.protected,
        build.bare,
        tmp_path / "integration",
        build.registry,
    )
    assert result.review is not None
    assert result.status == ("FAILED" if wrong_combined_output else "WAITING_APPROVAL")
    assert result.review.passed is not wrong_combined_output
    assert (result.review.approval is None) is wrong_combined_output
    assert _git(build.bare, "rev-parse", "refs/heads/main") == build.base
    assert _git(build.bare, "show", result.review.candidate_commit + ":answer.txt") == "verified"
    assert _git(build.bare, "show", result.review.candidate_commit + ":part1.txt") == (
        "wrong output" if wrong_combined_output else "second worker"
    )
    report = json.loads(build.service.store.read_blob(result.report_sha256))
    assert len(report["handoff_sha256"]) == 2 and report["candidate_commit"] == result.review.candidate_commit
    with connected(build)() as c:
        assert c.execute("SELECT status FROM panestria.goal WHERE id=%s", (plan.goal_id,)).fetchone() == ("ACTIVE",)
        assert c.execute(
            "SELECT count(*) FROM panestria.approval_request WHERE goal_id=%s", (plan.goal_id,)
        ).fetchone() == ((0 if wrong_combined_output else 1),)

    if not wrong_combined_output:
        pending = owner.status(plan.goal_id, diff=True)
        assert pending["task_id"] == final.lease.task_id and "part1.txt" in pending["diff"]
        approval = pending["approval"]
        merged = owner.approve(
            approval["approval_id"], approval["effect_digest"], approval["expected_version"], str(uuid4())
        )
        assert merged["task_state"] == "COMPLETED"
        with connected(build)() as c:
            assert c.execute("SELECT count(*) FROM panestria.build_active_worker_claim").fetchone() == (0,)
            assert c.execute(
                "SELECT reason FROM panestria.build_claim_release WHERE attempt_id=%s", (final.lease.attempt_id,)
            ).fetchone() == ("VERIFIED_FINAL",)
        assert _git(build.bare, "rev-parse", "refs/heads/main") == result.review.candidate_commit
        assert _git(build.source, "rev-parse", "HEAD") == candidate2  # Original worker checkout preserved.
        # A historical confirmed release stays idempotent after owner revocation.
        from panestria.kernel.plan_lifecycle import PlanLifecycle
        from panestria.kernel.policy import PolicyService

        changed = build.policy.model_copy(
            update={
                "version": 3,
                "autonomy": build.policy.autonomy.model_copy(
                    update={
                        "version": 3,
                        "actions": {**build.policy.autonomy.actions, "read": "observe", "edit": "observe"},
                    }
                ),
            }
        )
        policy_service = PolicyService(build.certificates)
        with connected(build)() as c:
            review = policy_service.propose(UnitOfWork(c), build.actor, build.task["task"], changed)
        with connected(build)() as c:
            policy_service.decide(UnitOfWork(c), build.actor, review.review_id, review.effect_digest, "approve")
        with connected(build)() as c:
            policy_service.apply(UnitOfWork(c), build.actor, review.review_id, review.effect_digest)
        with connected(build)() as c:
            effect_id = c.execute(
                "SELECT id::text FROM panestria.side_effect WHERE task_id=%s", (final.lease.task_id,)
            ).fetchone()[0]
            PlanLifecycle().release_final(
                UnitOfWork(c),
                build.actor,
                plan.plan_id,
                final.lease.task_id,
                result.review.evidence_sha256,
                effect_id,
                build.service,
            )
            assert c.execute(
                "SELECT count(*) FROM panestria.task_event WHERE kind='build.plan.final_capacity_released'"
            ).fetchone() == (1,)


@pytest.mark.parametrize("build", [PATHS], indirect=True)
def test_conflicting_verified_edits_stop_without_candidate_pass_or_merge(build, tmp_path):
    plan = accepted(
        build,
        overlap=True,
        base_snapshot_sha=materialize(build.bare, build.base, build.base, tmp_path / "inventory").manifest_sha256,
    )
    one = claim(build, plan)
    assert isinstance(one, Scheduled)
    sibling(build, plan, one, build.candidate, tmp_path / "verified-one")
    two = claim(build, plan)  # Same-path work is serialized, never overwritten.
    assert isinstance(two, Scheduled)
    candidate2 = second_candidate(build, "answer.txt", "conflicting second edit")
    sibling(build, plan, two, candidate2, tmp_path / "verified-two")
    final = claim(build, plan)
    assert isinstance(final, Scheduled)
    result = BuildIntegrator(connected(build), build.actor, build.service, build.certificates).verify_for_review(
        plan.plan_id,
        final.lease.attempt_id,
        final.lease.epoch,
        build.protected,
        build.bare,
        tmp_path / "conflicting-integration",
        build.registry,
    )
    assert result.status == "CONFLICT" and result.review is None
    report = json.loads(build.service.store.read_blob(result.report_sha256))
    assert report["candidate_commit"] is None and report["conflicts"][0]["path"] == "answer.txt"
    assert not (tmp_path / "conflicting-integration" / "combined").exists()
    assert _git(build.bare, "rev-parse", "refs/heads/main") == build.base
    with connected(build)() as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.build_evidence WHERE task_id=%s", (final.lease.task_id,)
        ).fetchone() == (0,)
        assert c.execute(
            "SELECT count(*) FROM panestria.approval_request WHERE goal_id=%s", (plan.goal_id,)
        ).fetchone() == (0,)


@pytest.mark.parametrize("build", [PATHS], indirect=True)
def test_cancellation_after_actual_full_checks_cannot_publish_or_request_merge(build, tmp_path, monkeypatch):
    import panestria.execution.build_plan as module
    from panestria.kernel.plan_lifecycle import PlanLifecycle

    plan = accepted(
        build, base_snapshot_sha=materialize(build.bare, build.base, build.base, tmp_path / "inventory").manifest_sha256
    )
    one, two = claim(build, plan), claim(build, plan)
    assert isinstance(one, Scheduled) and isinstance(two, Scheduled)
    sibling(build, plan, one, build.candidate, tmp_path / "verified-one")
    sibling(build, plan, two, second_candidate(build, "part1.txt", "second worker"), tmp_path / "verified-two")
    final = claim(build, plan)
    assert isinstance(final, Scheduled)
    original = module.verify_build

    def checked_then_cancelled(*args, **kwargs):
        actual = original(*args, **kwargs)
        assert actual.bundle.passed()
        with connected(build)() as c:
            stop = PlanLifecycle().cancel(UnitOfWork(c), build.actor, plan.plan_id, plan.sha256())
            assert stop.status == "CANCEL_REQUESTED" and stop.held_claims == 1
            assert c.execute("SELECT state FROM panestria.task WHERE id=%s", (final.lease.task_id,)).fetchone() == (
                "CANCELLING",
            )
            assert c.execute(
                "SELECT state FROM panestria.worker_invocation WHERE attempt_id=%s "
                "AND binding->>'kind'='build-integration'",
                (final.lease.attempt_id,),
            ).fetchone() == ("CLAIMED",)
        return actual

    monkeypatch.setattr(module, "verify_build", checked_then_cancelled)
    with pytest.raises(KernelDenied, match="stale_lease"):
        BuildIntegrator(connected(build), build.actor, build.service, build.certificates).verify_for_review(
            plan.plan_id,
            final.lease.attempt_id,
            final.lease.epoch,
            build.protected,
            build.bare,
            tmp_path / "cancelled-integration",
            build.registry,
        )
    with connected(build)() as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.build_evidence WHERE task_id=%s", (final.lease.task_id,)
        ).fetchone() == (0,)
        assert c.execute(
            "SELECT count(*) FROM panestria.approval_request WHERE goal_id=%s", (plan.goal_id,)
        ).fetchone() == (0,)
    assert _git(build.bare, "rev-parse", "refs/heads/main") == build.base


@pytest.mark.parametrize("build", [PATHS], indirect=True)
def test_uncertain_verifier_cleanup_retains_claim_and_cannot_publish_or_redispatch(build, tmp_path, monkeypatch):
    from panestria.verification.runner import CheckResult
    from panestria.verification.sandboxed import SandboxedCheckRunner

    plan = accepted(
        build, base_snapshot_sha=materialize(build.bare, build.base, build.base, tmp_path / "inventory").manifest_sha256
    )
    one, two = claim(build, plan), claim(build, plan)
    assert isinstance(one, Scheduled) and isinstance(two, Scheduled)
    sibling(build, plan, one, build.candidate, tmp_path / "verified-one")
    sibling(build, plan, two, second_candidate(build, "part1.txt", "second worker"), tmp_path / "verified-two")
    final = claim(build, plan)
    assert isinstance(final, Scheduled)
    actual = SandboxedCheckRunner.run

    def lost_cleanup(self, *args, **kwargs):
        actual(self, *args, **kwargs)  # Real owned Docker job runs and cleans; simulate a lost cleanup receipt.
        return CheckResult(args[0], "FAIL", "sandbox_launch_reconciliation_required")

    monkeypatch.setattr(SandboxedCheckRunner, "run", lost_cleanup)
    integrator = BuildIntegrator(connected(build), build.actor, build.service, build.certificates)
    outcome = integrator.verify_for_review(
        plan.plan_id,
        final.lease.attempt_id,
        final.lease.epoch,
        build.protected,
        build.bare,
        tmp_path / "unconfirmed",
        build.registry,
    )
    assert outcome.status == "RECONCILING" and outcome.review is None
    with connected(build)() as c:
        assert c.execute(
            "SELECT state FROM panestria.worker_invocation WHERE attempt_id=%s "
            "AND binding->>'kind'='build-integration'",
            (final.lease.attempt_id,),
        ).fetchone() == ("UNKNOWN",)
        assert c.execute(
            "SELECT count(*) FROM panestria.build_active_worker_claim WHERE plan_id=%s", (plan.plan_id,)
        ).fetchone() == (1,)
        assert c.execute(
            "SELECT count(*) FROM panestria.build_evidence WHERE task_id=%s", (final.lease.task_id,)
        ).fetchone() == (0,)
    with pytest.raises(KernelDenied):
        integrator.verify_for_review(
            plan.plan_id,
            final.lease.attempt_id,
            final.lease.epoch,
            build.protected,
            build.bare,
            tmp_path / "do-not-replay",
            build.registry,
        )
    assert not (tmp_path / "do-not-replay").exists()
    assert _git(build.bare, "rev-parse", "refs/heads/main") == build.base
