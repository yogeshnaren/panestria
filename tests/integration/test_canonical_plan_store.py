"""Actual PostgreSQL/Git/CAS plans and controller evidence; no worker/runtime qualification."""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest
from build_support import _bundle
from build_support import build as build  # noqa: F401 -- real scoped PG/Git/CAS fixture

from panestria.contracts.goal import contract_sha256
from panestria.contracts.plan import HandoffSubmission, PlanNode, PlanProposal, ProjectInventory, WorkerInventory
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.leases import LeaseService
from panestria.kernel.plan_scope import task_plan_scope
from panestria.kernel.plan_store import PlanStore
from panestria.kernel.tasks import TaskService
from panestria.kernel.uow import UnitOfWork

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def r1_task(r1_migration_task):
    return r1_migration_task


def migrate(dsn, direction, target):
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "migrations/alembic.ini", direction, target],
        cwd=ROOT,
        env={**os.environ, "PANESTRIA_DATABASE_URL": dsn},
        capture_output=True,
        timeout=30,
    )


@pytest.fixture
def planned(build):  # noqa: F811
    inventory = ProjectInventory(
        owner_id=build.actor.owner_id,
        project_id=build.actor.project_id,
        base_commit=build.base,
        snapshot_sha256=build.snapshot.manifest_sha256,
        workers=(
            WorkerInventory(
                worker_ref="synthetic-controller-fixture",
                binary_sha256="ab" * 32,
                profile_sha256="cd" * 32,
                capabilities=("scoped-file-edit",),
                maximum_parallel=1,
            ),
        ),
    )
    first, second = str(uuid4()), str(uuid4())
    nodes = tuple(
        PlanNode(
            task_id=identifier,
            depends_on=() if i == 0 else (first,),
            worker_ref="synthetic-controller-fixture",
            capabilities=("scoped-file-edit",),
            paths=("answer.txt",),
            acceptance_keys=tuple(c.id for c in build.contract.acceptance),
            expected_artifacts=("patch",),
            attempts=1,
            wall_seconds_per_attempt=20,
            api_microusd_per_attempt=0,
        )
        for i, identifier in enumerate((first, second))
    )
    proposal = PlanProposal(
        plan_id=str(uuid4()),
        owner_id=build.actor.owner_id,
        project_id=build.actor.project_id,
        goal_id=build.task["goal"],
        contract_sha256=contract_sha256(build.contract),
        inventory_sha256=inventory.sha256(),
        privacy_class=build.contract.privacy_class,
        nodes=nodes,
    )
    return build, proposal, inventory, PlanStore()


def prepare(f):
    build, proposal, inventory, service = f
    with psycopg.connect(build.task["dsn"]) as c:
        return service.prepare(UnitOfWork(c), build.actor, proposal, inventory)


def accept(f, retained):
    build, proposal, _, service = f
    with psycopg.connect(build.task["dsn"]) as c:
        return service.accept(UnitOfWork(c), build.actor, proposal.plan_id, retained.effect_digest, accept_plan=True)


def test_proposal_is_scoped_immutable_and_does_not_create_tasks_or_permissions(planned):
    build, proposal, inventory, service = planned
    with psycopg.connect(build.task["dsn"]) as c:
        c.execute("SET LOCAL TIME ZONE 'America/Los_Angeles'")
        retained = service.prepare(UnitOfWork(c), build.actor, proposal, inventory)
    assert retained.consent.expires_at.endswith("+00:00")
    assert retained.state == "PROPOSED" and retained.execution_authority == "NONE"
    assert prepare(planned) == retained
    with psycopg.connect(build.task["dsn"]) as c:
        assert c.execute("SELECT count(*) FROM panestria.build_plan WHERE id=%s", (proposal.plan_id,)).fetchone() == (
            1,
        )
        assert c.execute(
            "SELECT count(*) FROM panestria.build_plan_task WHERE plan_id=%s", (proposal.plan_id,)
        ).fetchone() == (0,)
        assert c.execute(
            "SELECT count(*) FROM panestria.task WHERE id=ANY(%s::uuid[])", ([node.task_id for node in proposal.nodes],)
        ).fetchone() == (0,)
        for actor in (Actor(str(uuid4()), build.actor.project_id), Actor(build.actor.owner_id, str(uuid4()))):
            with pytest.raises(KernelDenied, match="not_found"), c.transaction():
                service.get(UnitOfWork(c), actor, proposal.plan_id)
        with pytest.raises(psycopg.Error), c.transaction():
            c.execute("UPDATE panestria.build_plan SET version=2 WHERE id=%s", (proposal.plan_id,))
        with pytest.raises(KernelDenied, match="plan_revision_not_admitted"), c.transaction():
            service.prepare(
                UnitOfWork(c), build.actor, proposal.model_copy(update={"plan_id": str(uuid4())}), inventory
            )


def test_exact_owner_acceptance_and_concurrency_create_one_canonical_dag(planned):
    build, proposal, _, service = planned
    retained = prepare(planned)
    with psycopg.connect(build.task["dsn"]) as c:
        with pytest.raises(KernelDenied, match="explicit_plan_acceptance"), c.transaction():
            service.accept(UnitOfWork(c), build.actor, proposal.plan_id, retained.effect_digest, accept_plan=False)
        with pytest.raises(KernelDenied, match="plan_review_changed"), c.transaction():
            service.accept(UnitOfWork(c), build.actor, proposal.plan_id, "ff" * 32, accept_plan=True)
    barrier = Barrier(2)

    def one():
        barrier.wait(timeout=10)
        return accept(planned, retained)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(one) for _ in range(2)]
        results = [future.result(timeout=30) for future in futures]
    assert results[0] == results[1] and results[0].state == "ACCEPTED"
    assert results[0].execution_authority == "NONE"
    with psycopg.connect(build.task["dsn"]) as c:
        rows = c.execute(
            "SELECT state,max_attempts FROM panestria.task WHERE id=ANY(%s::uuid[])",
            ([n.task_id for n in proposal.nodes],),
        ).fetchall()
        assert rows == [("CREATED", 1), ("CREATED", 1)]
        assert c.execute(
            "SELECT task_id::text,depends_on::text FROM panestria.task_dependency WHERE task_id=%s",
            (proposal.nodes[1].task_id,),
        ).fetchall() == [(proposal.nodes[1].task_id, proposal.nodes[0].task_id)]
        assert c.execute(
            "SELECT count(*) FROM panestria.task_event WHERE goal_id=%s AND kind='build.plan.accepted'",
            (proposal.goal_id,),
        ).fetchone() == (1,)
        assert c.execute(
            "SELECT count(*) FROM panestria.approval_request WHERE goal_id=%s", (proposal.goal_id,)
        ).fetchone() == (0,)
        assert service.get(UnitOfWork(c), build.actor, proposal.plan_id) == results[0]


def test_acceptance_state_tasks_and_event_rollback_together(planned):
    build, proposal, _, service = planned
    retained = prepare(planned)
    with psycopg.connect(build.task["dsn"]) as c:
        service.accept(UnitOfWork(c), build.actor, proposal.plan_id, retained.effect_digest, accept_plan=True)
        c.rollback()
        assert service.get(UnitOfWork(c), build.actor, proposal.plan_id).state == "PROPOSED"
        assert c.execute(
            "SELECT count(*) FROM panestria.build_plan_acceptance WHERE plan_id=%s", (proposal.plan_id,)
        ).fetchone() == (0,)
        assert c.execute(
            "SELECT count(*) FROM panestria.task_event WHERE goal_id=%s AND kind='build.plan.accepted'",
            (proposal.goal_id,),
        ).fetchone() == (0,)
    assert accept(planned, retained).state == "ACCEPTED"


def test_handoff_reconstructs_current_verified_source_without_completing_or_merging(planned):
    build, proposal, _, service = planned
    retained = prepare(planned)
    accept(planned, retained)
    task = proposal.nodes[0].task_id
    with psycopg.connect(build.task["dsn"]) as c:
        TaskService().transition(
            UnitOfWork(c),
            build.actor,
            task,
            0,
            0,
            "VALIDATING",
            "fixture",
            policy_version=build.contract.autonomy_profile_ref,
            correlation_id=str(uuid4()),
        )
    with psycopg.connect(build.task["dsn"]) as c:
        TaskService().transition(
            UnitOfWork(c),
            build.actor,
            task,
            1,
            0,
            "READY",
            "fixture",
            policy_version=build.contract.autonomy_profile_ref,
            correlation_id=str(uuid4()),
        )
    with psycopg.connect(build.task["dsn"]) as c:
        lease = LeaseService().acquire(
            UnitOfWork(c), build.actor, task, "synthetic-controller-fixture", 2, ttl_seconds=120
        )
    current = replace(build, task={**build.task, "task": task}, attempt=lease.attempt_id)
    with psycopg.connect(build.task["dsn"]) as c:
        scope = task_plan_scope(UnitOfWork(c), build.actor, task)
    bundle = _bundle(current, plan_scope=scope)
    with psycopg.connect(build.task["dsn"]) as c:
        digest = build.service.publish(UnitOfWork(c), build.actor, bundle)
    with psycopg.connect(build.task["dsn"]) as c:
        version = c.execute("SELECT row_version FROM panestria.task WHERE id=%s", (task,)).fetchone()[0]
    submission = HandoffSubmission(
        handoff_id=str(uuid4()),
        plan_id=proposal.plan_id,
        task_id=task,
        expected_task_version=version,
        evidence_sha256=digest,
        next_tasks=(proposal.nodes[1].task_id,),
        summary="Untrusted worker note: done",
    )
    with psycopg.connect(build.task["dsn"]) as c:
        handoff = service.handoff(UnitOfWork(c), build.actor, submission, build.service)
    assert handoff.candidate_commit == build.candidate and handoff.candidate_tree == build.snapshot.tree
    assert handoff.task_completion_authority == "NONE" and handoff.summary_authority == "UNTRUSTED_NOTE"
    assert handoff.runtime_qualification == "NOT_ASSESSED"
    with psycopg.connect(build.task["dsn"]) as c:
        assert service.read_handoff(UnitOfWork(c), build.actor, submission.handoff_id, build.service) == handoff
        assert service.handoff(UnitOfWork(c), build.actor, submission, build.service) == handoff
        assert c.execute("SELECT state FROM panestria.task WHERE id=%s", (task,)).fetchone() == ("VERIFYING",)
        assert c.execute(
            "SELECT count(*) FROM panestria.task_event WHERE task_id=%s AND kind='build.plan.handoff'", (task,)
        ).fetchone() == (1,)
        with pytest.raises(KernelDenied, match="handoff_conflict"), c.transaction():
            service.handoff(
                UnitOfWork(c), build.actor, submission.model_copy(update={"summary": "changed"}), build.service
            )
        c.execute("UPDATE panestria.task SET lease_epoch=lease_epoch+1 WHERE id=%s", (task,))
        with pytest.raises(KernelDenied, match="stale_build_evidence"), c.transaction():
            service.read_handoff(UnitOfWork(c), build.actor, submission.handoff_id, build.service)


def test_caller_transaction_and_populated_migration_preserve_audit(planned):
    build, proposal, _, service = planned
    assert migrate(build.task["dsn"], "downgrade", "0032_structured_style").returncode == 0
    assert migrate(build.task["dsn"], "upgrade", "head").returncode == 0
    prepare(planned)
    with psycopg.connect(build.task["dsn"], autocommit=True) as c:
        with pytest.raises(KernelDenied, match="plan_caller_transaction_required"):
            service.get(UnitOfWork(c), build.actor, proposal.plan_id)
    refused = migrate(build.task["dsn"], "downgrade", "0032_structured_style")
    assert refused.returncode != 0 and b"canonical plan audit exists" in refused.stderr
    with psycopg.connect(build.task["dsn"]) as c:
        assert c.execute("SELECT version_num FROM alembic_version").fetchone() == ("0033_canonical_plans",)
        assert service.get(UnitOfWork(c), build.actor, proposal.plan_id).state == "PROPOSED"
        with pytest.raises(psycopg.Error), c.transaction():
            c.execute("DELETE FROM panestria.build_plan WHERE id=%s", (proposal.plan_id,))


def _lease_node(planned, task):
    build = planned[0]
    with psycopg.connect(build.task["dsn"]) as c:
        for version, target in enumerate(("VALIDATING", "READY")):
            TaskService().transition(
                UnitOfWork(c),
                build.actor,
                task,
                version,
                0,
                target,
                "accepted-plan-controller-fixture",
                policy_version=build.contract.autonomy_profile_ref,
                correlation_id=str(uuid4()),
            )
        lease = LeaseService().acquire(
            UnitOfWork(c), build.actor, task, "synthetic-controller-fixture", 2, ttl_seconds=120
        )
        scope = task_plan_scope(UnitOfWork(c), build.actor, task)
    return replace(build, task={**build.task, "task": task}, attempt=lease.attempt_id), scope


def test_intermediate_all_check_pass_cannot_request_any_protected_merge(planned):
    from panestria.kernel.approvals import ApprovalService

    build, proposal, _, _ = planned
    accept(planned, prepare(planned))
    current, scope = _lease_node(planned, proposal.nodes[0].task_id)
    bundle = _bundle(current, plan_scope=scope)
    with psycopg.connect(build.task["dsn"]) as c:
        digest = build.service.publish(UnitOfWork(c), build.actor, bundle)
    with psycopg.connect(build.task["dsn"]) as c:
        assert build.service.current(UnitOfWork(c), build.actor, current.task["task"], digest) == bundle
        with pytest.raises(KernelDenied, match="plan_node_cannot_merge_goal"), c.transaction():
            build.service.request_merge(UnitOfWork(c), build.actor, current.task["task"], digest, "refs/heads/main")
        # Even the generic approval API cannot turn this intermediate result
        # into a merge. The same complete check set remains required there.
        original = _bundle(build)
        root_digest = build.service.publish(UnitOfWork(c), build.actor, original)
        review = build.service.request_merge(
            UnitOfWork(c), build.actor, build.task["task"], root_digest, "refs/heads/main"
        )
        preview = {**review.preview, "task_id": current.task["task"], "candidate_sha256": digest}
        with pytest.raises(KernelDenied, match="plan_node_cannot_merge_goal"), c.transaction():
            ApprovalService().request(UnitOfWork(c), build.actor, preview)
        assert c.execute("SELECT state FROM panestria.task WHERE id=%s", (current.task["task"],)).fetchone() == (
            "VERIFYING",
        )


@pytest.mark.parametrize("build", [("answer.txt", "notes.txt")], indirect=True)
def test_node_subset_and_paths_come_from_accepted_membership_not_worker_choice(planned):
    from build_support import _git

    from panestria.verification.build import verify_build
    from panestria.verification.git_snapshot import materialize

    build, proposal, inventory, service = planned
    first = proposal.nodes[0].model_copy(update={"acceptance_keys": ("AC-002",)})
    proposal = proposal.model_copy(update={"nodes": (first, proposal.nodes[1])})
    planned = build, proposal, inventory, service
    accept(planned, prepare(planned))
    current, scope = _lease_node(planned, first.task_id)
    assert scope is not None and not scope.integration
    bundle = _bundle(current, plan_scope=scope)
    assert len(bundle.checks) == 1
    with psycopg.connect(build.task["dsn"]) as c:
        # Missing canonical scope, extra checks or a different node hash cannot
        # substitute for the explicitly accepted subset.
        with pytest.raises(KernelDenied, match="build_plan_scope_mismatch|build_check_set_mismatch"), c.transaction():
            build.service.publish(UnitOfWork(c), build.actor, _bundle(current))
    kwargs = dict(
        contract=build.contract,
        contract_id=build.task["contract"],
        task_id=first.task_id,
        attempt_id=current.attempt,
        epoch=1,
        base=build.base,
        candidate=build.candidate,
        snapshot=build.snapshot,
        check_ids=build.ids,
        registry=build.registry,
        policy=build.policy,
    )
    verified = verify_build(**kwargs, plan_scope=scope)
    assert verified.bundle.passed() and [x.check_key for x in verified.bundle.checks] == ["AC-002"]
    (build.source / "notes.txt").write_text("outside this node, inside the goal")
    _git(build.source, "add", "notes.txt")
    _git(build.source, "commit", "-m", "synthetic other-node edit")
    candidate = _git(build.source, "rev-parse", "HEAD")
    _git(build.bare, "fetch", str(build.source), candidate)
    snapshot = materialize(build.bare, build.base, candidate, build.snapshot.directory.parent / "other-node")
    outside = verify_build(**{**kwargs, "snapshot": snapshot, "candidate": candidate}, plan_scope=scope)
    assert not outside.bundle.passed()
    # A wider counterfactual scope passes the goal's path rule, but is not the
    # accepted node scope and its reports cannot be published for this node.
    widened = scope.model_copy(update={"node": first.model_copy(update={"paths": ("answer.txt", "notes.txt")})})
    wider = verify_build(**{**kwargs, "snapshot": snapshot, "candidate": candidate}, plan_scope=widened)
    assert wider.bundle.passed()
    with psycopg.connect(build.task["dsn"]) as c:
        for raw in wider.reports:
            build.service.store.write_report(raw)
        with pytest.raises(KernelDenied, match="build_plan_scope_mismatch"), c.transaction():
            build.service.publish(UnitOfWork(c), build.actor, wider.bundle)
        assert c.execute(
            "SELECT count(*) FROM panestria.build_evidence WHERE task_id=%s", (first.task_id,)
        ).fetchone() == (0,)
        digest = build.service.publish(UnitOfWork(c), build.actor, bundle)
        assert build.service.current(UnitOfWork(c), build.actor, first.task_id, digest).passed()
