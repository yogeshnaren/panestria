"""Actual completed sibling results, conflict detection and full Docker verification.

Workers/capacity are controller fixtures, not native vendor/OS qualification.
"""

import hashlib
import json
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
from panestria.verification.git_snapshot import materialize


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
        assert _git(build.bare, "rev-parse", "refs/heads/main") == result.review.candidate_commit
        assert _git(build.source, "rev-parse", "HEAD") == candidate2  # Original worker checkout preserved.


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
    from uuid import uuid4

    import panestria.execution.build_plan as module
    from panestria.kernel.tasks import TaskService

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
            version = c.execute(
                "SELECT row_version FROM panestria.task WHERE id=%s", (final.lease.task_id,)
            ).fetchone()[0]
            TaskService().transition(
                UnitOfWork(c),
                build.actor,
                final.lease.task_id,
                version,
                final.lease.epoch,
                "CANCELLING",
                "owner-cancel",
                policy_version=build.contract.autonomy_profile_ref,
                correlation_id=str(uuid4()),
            )
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
