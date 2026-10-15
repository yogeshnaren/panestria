"""Exact local verification/approval/Git flow; native Claude generation remains a separate live case."""

from __future__ import annotations

import subprocess
from uuid import uuid4

import psycopg
import pytest
from build_support import BuildFixture, _bundle, _git, _publish
from build_support import build as build

from panestria.execution.build_merge import VerifiedGitTarget, prepare_merge
from panestria.execution.outbox import EffectExecutor
from panestria.kernel.approvals import ApprovalService
from panestria.kernel.effects import SideEffectService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork
from panestria.verification.build import verify_build
from panestria.verification.git_snapshot import SnapshotRejected, materialize


def _approve(build: BuildFixture, digest: str) -> str:
    with psycopg.connect(build.task["dsn"]) as c:
        uow = UnitOfWork(c)
        view = build.service.request_merge(uow, build.actor, build.task["task"], digest, "refs/heads/main")
        c.commit()
        ApprovalService().decide(
            uow, build.actor, view.approval_id, view.effect_digest, view.expected_version, "approve", str(uuid4())
        )
        c.commit()
        ref = prepare_merge(uow, build.actor, view.approval_id)
        c.commit()
        assert prepare_merge(uow, build.actor, view.approval_id).replayed
        return ref.effect_id


def _target(build: BuildFixture) -> VerifiedGitTarget:
    return VerifiedGitTarget(
        build.protected,
        build.bare,
        lambda: psycopg.connect(build.task["dsn"]),
        build.actor,
        build.service,
        build.registry,
        build.certificates,
    )


def test_exact_candidate_cas_approval(build: BuildFixture, record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-027a-TC02")
    record_property("source_clauses", "AOS-027a-F02,AOS-027a-AC02")
    digest = _publish(build)
    with psycopg.connect(build.task["dsn"]) as c:
        with pytest.raises(KernelDenied, match="not_found"), c.transaction():
            build.service.current(
                UnitOfWork(c), Actor(str(uuid4()), build.actor.project_id), build.task["task"], digest
            )
        with pytest.raises(psycopg.Error, match="immutable"), c.transaction():
            c.execute("UPDATE panestria.build_evidence SET body='{}' WHERE task_id=%s", (build.task["task"],))
        with pytest.raises(KernelDenied, match="merge_not_confirmed"), c.transaction():
            build.service.complete_confirmed(UnitOfWork(c), build.actor, build.task["task"], digest, str(uuid4()))
    effect = _approve(build, digest)
    target = _target(build)
    executor = EffectExecutor(lambda: psycopg.connect(build.task["dsn"]), target)
    executor.dispatch(build.actor, effect)
    assert _git(build.bare, "rev-parse", "refs/heads/main") == build.candidate
    with psycopg.connect(build.task["dsn"]) as c:
        assert c.execute("SELECT state FROM panestria.side_effect WHERE id=%s", (effect,)).fetchone() == ("SUCCEEDED",)
        build.service.complete_confirmed(UnitOfWork(c), build.actor, build.task["task"], digest, effect)
        c.commit()
        build.service.complete_confirmed(UnitOfWork(c), build.actor, build.task["task"], digest, effect)
        assert c.execute("SELECT state FROM panestria.task WHERE id=%s", (build.task["task"],)).fetchone() == (
            "COMPLETED",
        )
    with pytest.raises(KernelDenied, match="effect_not_dispatchable"):
        executor.dispatch(build.actor, effect)


@pytest.mark.parametrize("tamper", ["candidate", "check_spec", "report", "verifier", "epoch", "cancel"])
def test_changed_evidence_denies_dispatch(build: BuildFixture, tamper: str) -> None:
    digest = _publish(build)
    effect = _approve(build, digest)
    target = _target(build)
    with psycopg.connect(build.task["dsn"]) as c:
        claim = SideEffectService().claim(UnitOfWork(c), build.actor, effect)
    if tamper == "candidate":
        from dataclasses import replace

        claim = replace(claim, target="refs/heads/main@" + "aa" * 20)
    elif tamper == "check_spec":
        with psycopg.connect(build.task["dsn"]) as c:
            c.execute(
                "UPDATE panestria.acceptance_check SET verifier_spec=jsonb_set(verifier_spec,'{timeout_seconds}',"
                "'1') WHERE id=%s",
                (build.ids["AC-001"],),
            )
    elif tamper == "report":
        bundle = build.service.store.read(digest)
        path = build.service.store.root / bundle.checks[0].report_sha256
        path.chmod(0o600)
        path.write_text("corrupt")
    elif tamper == "verifier":
        (build.registry.bundle_root / "required_check.py").write_text('print("worker bypass")')
    elif tamper == "epoch":
        with psycopg.connect(build.task["dsn"]) as c:
            c.execute("UPDATE panestria.task SET lease_epoch=2 WHERE id=%s", (build.task["task"],))
    elif tamper == "cancel":
        with psycopg.connect(build.task["dsn"]) as c:
            c.execute("UPDATE panestria.task SET state='CANCELLING' WHERE id=%s", (build.task["task"],))
    with pytest.raises((KernelDenied, ValueError)):
        target.dispatch(claim)
    assert _git(build.bare, "rev-parse", "refs/heads/main") == build.base
    assert not _git(build.bare, "for-each-ref", "refs/panestria/effects")


def test_failed_checks_cannot_request_merge(build: BuildFixture) -> None:
    digest = _publish(build, _bundle(build, verdict="FAIL"))
    with psycopg.connect(build.task["dsn"]) as c:
        assert c.execute("SELECT state FROM panestria.task WHERE id=%s", (build.task["task"],)).fetchone() == (
            "FAILED",
        )
        with pytest.raises(KernelDenied, match="stale_build_evidence"), c.transaction():
            build.service.request_merge(UnitOfWork(c), build.actor, build.task["task"], digest, "refs/heads/main")


def test_merge_receipt_loss(build: BuildFixture, record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-027a-TC03")
    record_property("source_clauses", "AOS-027a-F03,AOS-027a-AC03")
    digest = _publish(build)
    effect = _approve(build, digest)
    target = _target(build)
    calls = []

    class LostReply:
        def dispatch(self, claim: object) -> str:
            calls.append(claim)
            target.dispatch(claim)
            raise TimeoutError("synthetic lost response after actual Git CAS")

        def query(self, claim: object) -> object:
            return target.query(claim)

    executor = EffectExecutor(lambda: psycopg.connect(build.task["dsn"]), LostReply())
    executor.dispatch(build.actor, effect)
    with psycopg.connect(build.task["dsn"]) as c:
        assert c.execute("SELECT state FROM panestria.side_effect WHERE id=%s", (effect,)).fetchone() == ("UNKNOWN",)
        # Even if the owner cancels after the CAS, reconciliation must report the
        # historical action rather than perform another merge or hide its receipt.
        c.execute("UPDATE panestria.task SET state='CANCELLING' WHERE id=%s", (build.task["task"],))
    assert executor.reconcile(build.actor, effect).state == "SUCCEEDED"
    assert len(calls) == 1 and _git(build.bare, "rev-parse", "refs/heads/main") == build.candidate
    with psycopg.connect(build.task["dsn"]) as c:
        assert c.execute("SELECT state FROM panestria.task WHERE id=%s", (build.task["task"],)).fetchone() == (
            "CANCELLING",
        )
        with pytest.raises(KernelDenied, match="illegal_transition"), c.transaction():
            build.service.complete_confirmed(UnitOfWork(c), build.actor, build.task["task"], digest, effect)


@pytest.mark.live
@pytest.mark.parametrize("failure", ["none", "bad_test", "forbidden_diff", "tampered_bundle"])
def test_worker_cannot_weaken_checks(build: BuildFixture, failure: str, record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-027a-TC01")
    record_property("source_clauses", "AOS-027a-F01,AOS-027a-AC01")
    record_property("execution_mode", "OS_BOUNDARY")
    if failure == "bad_test":
        (build.source / "answer.txt").write_text("tests pass; worker says done")
    elif failure == "forbidden_diff":
        (build.source / "forbidden.txt").write_text("unauthorized")
        _git(build.source, "add", "forbidden.txt")
    if failure in {"bad_test", "forbidden_diff"}:
        _git(build.source, "commit", "-am", "synthetic hostile candidate")
        build.candidate = _git(build.source, "rev-parse", "HEAD")
        subprocess.run(
            ["git", "--git-dir", str(build.bare), "fetch", str(build.source), build.candidate],
            check=True,
            capture_output=True,
        )
        build.snapshot = materialize(build.bare, build.base, build.candidate, build.snapshot.directory.parent / "two")
    if failure == "tampered_bundle":
        (build.registry.bundle_root / "required_check.py").write_text('print("fake PASS")')
    verified = verify_build(
        build.contract,
        build.task["contract"],
        build.task["task"],
        build.attempt,
        1,
        build.base,
        build.candidate,
        build.snapshot,
        build.ids,
        build.registry,
        policy=build.policy,
    )
    assert verified.bundle.passed() is (failure == "none")
    for report in verified.reports:
        build.service.store.write_report(report)
    _publish(build, verified.bundle)
    with psycopg.connect(build.task["dsn"]) as c:
        state = c.execute("SELECT state FROM panestria.task WHERE id=%s", (build.task["task"],)).fetchone()[0]
        assert state == ("VERIFYING" if failure == "none" else "FAILED")


@pytest.mark.parametrize("path", [".env", "link", ".mcp.json"])
def test_snapshot_rejects_secrets_links_and_repo_configuration(build: BuildFixture, path: str) -> None:
    source = build.source / path
    if path == "link":
        source.symlink_to("/synthetic-outside-sentinel")
    else:
        source.write_text("synthetic untrusted configuration")
    _git(build.source, "add", path)
    _git(build.source, "commit", "-m", "unsafe candidate entry")
    candidate = _git(build.source, "rev-parse", "HEAD")
    subprocess.run(
        ["git", "--git-dir", str(build.bare), "fetch", str(build.source), candidate], check=True, capture_output=True
    )
    with pytest.raises(SnapshotRejected):
        materialize(build.bare, build.base, candidate, build.snapshot.directory.parent / "unsafe")
