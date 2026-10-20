"""Real PG concurrency/rollback and Git/CAS path verification; capacity is a fixture.

No live workers, runtime certificate, quota measurement or host qualification is
claimed. Each test owns its own disposable database, including global fleet rows.
"""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest
from build_support import _git
from build_support import build as build  # noqa: F401

from panestria.contracts.goal import contract_sha256, load_contract
from panestria.contracts.hardware import HardwareManifest
from panestria.contracts.plan import HandoffSubmission, PlanNode, PlanProposal, ProjectInventory, WorkerInventory
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.plan_scope import task_plan_scope
from panestria.kernel.plan_store import PlanStore
from panestria.kernel.policy import PolicyService
from panestria.kernel.scheduler import Scheduled, Scheduler
from panestria.kernel.uow import UnitOfWork
from panestria.resources.hardware import PROBE_SHA256
from panestria.verification.build import verify_build
from panestria.verification.git_snapshot import materialize

PATHS = ("answer.txt", *(f"part{i}.txt" for i in range(1, 8)))


@pytest.fixture
def r1_task(r1_migration_task):
    return r1_migration_task


def migration(build, direction, revision):
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "migrations/alembic.ini", direction, revision],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PANESTRIA_DATABASE_URL": build.task["dsn"]},
        capture_output=True,
        timeout=30,
    )


def capacity(**changes):
    return HardwareManifest(
        observed_at=datetime.now(UTC),
        simulated=False,
        os="Linux",
        arch="fixture",
        kernel="fixture",
        cpu="fixture",
        logical_cores=8,
        ram_available_gib=16.0,
        disk_free_gib=20.0,
        accelerators=(),
        on_ac_power=True,
        gpu_status="NOT_PROBED_CPU_ONLY",
        probe_sha256=PROBE_SHA256,
        catalog_version="controller-fixture",
    ).model_copy(update=changes)


def reviewed_edit_policy(build):
    """Explicit synthetic owner review; never bypass scheduler approval policy."""
    policy = build.policy.model_copy(
        update={
            "version": 2,
            "autonomy": build.policy.autonomy.model_copy(
                update={
                    "version": 2,
                    "actions": {**build.policy.autonomy.actions, "edit": "act-and-report"},
                }
            ),
        }
    )
    service = PolicyService(build.certificates)
    with psycopg.connect(build.task["dsn"]) as c:
        review = service.propose(UnitOfWork(c), build.actor, build.task["task"], policy)
    with psycopg.connect(build.task["dsn"]) as c:
        service.decide(UnitOfWork(c), build.actor, review.review_id, review.effect_digest, "approve")
    with psycopg.connect(build.task["dsn"]) as c:
        policy = service.apply(UnitOfWork(c), build.actor, review.review_id, review.effect_digest)
    document = build.contract.model_dump(mode="json")
    document.update(contract_version=3, autonomy_profile_ref=f"project-policy:2:{policy.sha256()}")
    build.contract = load_contract(document)
    identifier = str(uuid4())
    build.ids = {check.id: str(uuid4()) for check in build.contract.acceptance}
    with psycopg.connect(build.task["dsn"]) as c:
        c.execute(
            "INSERT INTO panestria.goal_contract(id,goal_id,version,body,sha256) VALUES(%s,%s,3,%s::jsonb,%s)",
            (identifier, build.contract.goal_id, build.contract.model_dump_json(), contract_sha256(build.contract)),
        )
        c.execute("UPDATE panestria.task SET contract_id=%s WHERE id=%s", (identifier, build.task["task"]))
        for check in build.contract.acceptance:
            c.execute(
                "INSERT INTO panestria.acceptance_check(id,contract_id,check_key,description,required,"
                "verifier_type,verifier_spec) VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb)",
                (
                    build.ids[check.id],
                    identifier,
                    check.id,
                    check.description,
                    check.required,
                    check.verifier.type,
                    check.verifier.model_dump_json(),
                ),
            )
    build.task = {**build.task, "contract": identifier}
    build.policy = policy


def accepted(build, count=2, *, overlap=False, edit_grant=True):
    if edit_grant:
        reviewed_edit_policy(build)
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
                maximum_parallel=2,
            ),
        ),
    )
    ids = [str(uuid4()) for _ in range(count + 1)]
    nodes = tuple(
        PlanNode(
            task_id=identity,
            depends_on=tuple(ids[:-1]) if i == count else (),
            worker_ref="synthetic-controller-fixture",
            capabilities=("scoped-file-edit",),
            paths=PATHS[:count] if i == count else (PATHS[0] if overlap else PATHS[i],),
            acceptance_keys=tuple(c.id for c in build.contract.acceptance) if i == count else ("AC-002",),
            expected_artifacts=("patch",),
            attempts=1,
            wall_seconds_per_attempt=120 // len(ids),
            api_microusd_per_attempt=0,
        )
        for i, identity in enumerate(ids)
    )
    proposal = PlanProposal(
        plan_id=str(uuid4()),
        owner_id=build.actor.owner_id,
        project_id=build.actor.project_id,
        goal_id=build.contract.goal_id,
        contract_sha256=contract_sha256(build.contract),
        inventory_sha256=inventory.sha256(),
        privacy_class=build.contract.privacy_class,
        nodes=nodes,
    )
    with psycopg.connect(build.task["dsn"]) as c:
        store = PlanStore()
        retained = store.prepare(UnitOfWork(c), build.actor, proposal, inventory)
    with psycopg.connect(build.task["dsn"]) as c:
        store.accept(UnitOfWork(c), build.actor, proposal.plan_id, retained.effect_digest, accept_plan=True)
    return proposal


def claim(build, plan, cap=None):
    with psycopg.connect(build.task["dsn"]) as c:
        return Scheduler().claim_ready(UnitOfWork(c), build.actor, plan.plan_id, cap or capacity(), build.service)


@pytest.mark.parametrize("build", [PATHS], indirect=True)
def test_eight_competing_claims_reserve_only_two_and_expiry_does_not_free_capacity(build):
    plan = accepted(build, 8)
    barrier = Barrier(8)

    def one():
        barrier.wait(timeout=10)
        return claim(build, plan)

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(one) for _ in range(8)]
        results = [future.result(timeout=20) for future in futures]
    leased = [r for r in results if isinstance(r, Scheduled)]
    assert len(leased) == 2 and len({r.lease.task_id for r in leased}) == 2
    assert all(r.dispatch_authority == "NONE" for r in leased)
    with psycopg.connect(build.task["dsn"]) as c:
        assert c.execute("SELECT count(*) FROM panestria.build_worker_claim").fetchone() == (2,)
        assert c.execute(
            "SELECT count(*) FROM panestria.task_event WHERE kind='build.scheduler.claimed'"
        ).fetchone() == (2,)
        c.execute("UPDATE panestria.task_attempt SET lease_expires_at=clock_timestamp()-interval '1 hour'")
    queued = claim(build, plan)
    assert not isinstance(queued, Scheduled)
    assert any(s.reason == "fleet_limit" for s in queued)
    downgrade = migration(build, "downgrade", "0033_canonical_plans")
    assert downgrade.returncode != 0 and b"build claim audit exists" in downgrade.stderr
    with psycopg.connect(build.task["dsn"]) as c:
        with pytest.raises(psycopg.Error), c.transaction():
            c.execute("DELETE FROM panestria.build_worker_claim")
        assert all(r["capacity_held"] for r in Scheduler().claims(UnitOfWork(c), build.actor, plan.plan_id))
        assert c.execute("SELECT count(*) FROM panestria.build_worker_claim WHERE released_at IS NULL").fetchone() == (
            2,
        )


@pytest.mark.parametrize("build", [PATHS], indirect=True)
def test_claim_rolls_back_with_lease_and_event_and_preserves_scope_and_resource_waits(build):
    plan = accepted(build)
    assert migration(build, "downgrade", "0033_canonical_plans").returncode == 0
    assert migration(build, "upgrade", "head").returncode == 0
    with psycopg.connect(build.task["dsn"]) as c:
        result = Scheduler().claim_ready(UnitOfWork(c), build.actor, plan.plan_id, capacity(), build.service)
        assert isinstance(result, Scheduled)
        c.rollback()
        assert c.execute("SELECT count(*) FROM panestria.build_worker_claim").fetchone() == (0,)
        assert c.execute("SELECT state FROM panestria.task WHERE id=%s", (result.lease.task_id,)).fetchone() == (
            "CREATED",
        )
        assert c.execute(
            "SELECT count(*) FROM panestria.task_event WHERE kind='build.scheduler.claimed'"
        ).fetchone() == (0,)
        with pytest.raises(KernelDenied, match="not_found"), c.transaction():
            Scheduler().inspect(UnitOfWork(c), Actor(str(uuid4()), build.actor.project_id), plan.plan_id, build.service)
    for cap in (
        capacity(simulated=True),
        capacity(observed_at=datetime.now(UTC) - timedelta(seconds=31)),
        capacity(observed_at=datetime.now(UTC) + timedelta(seconds=10)),
    ):
        with pytest.raises(KernelDenied, match="fresh_actual_capacity_required"):
            claim(build, plan, cap)
    for cap in (capacity(ram_available_gib=4.0), capacity(disk_free_gib=2.0), capacity(on_ac_power=False)):
        assert any(s.reason == "foreground_capacity_wait" for s in claim(build, plan, cap))
    assert isinstance(claim(build, plan), Scheduled)


@pytest.mark.parametrize("build", [PATHS], indirect=True)
def test_overlapping_paths_queue_without_overwriting_other_work(build):
    plan = accepted(build, overlap=True)
    assert isinstance(claim(build, plan), Scheduled)
    queued = claim(build, plan)
    assert not isinstance(queued, Scheduled)
    assert queued[1].reason == "path_conflict" and queued[-1].reason == "dependency_not_verified"


def verified_handoff(build, plan, scheduled, candidate, directory):
    task = scheduled.lease.task_id
    snapshot = materialize(build.bare, build.base, candidate, directory)
    with psycopg.connect(build.task["dsn"]) as c:
        scope = task_plan_scope(UnitOfWork(c), build.actor, task)
    observed = verify_build(
        build.contract,
        build.task["contract"],
        task,
        scheduled.lease.attempt_id,
        scheduled.lease.epoch,
        build.base,
        candidate,
        snapshot,
        build.ids,
        build.registry,
        plan_scope=scope,
    )
    for report in observed.reports:
        build.service.store.write_report(report)
    with psycopg.connect(build.task["dsn"]) as c:
        digest = build.service.publish(UnitOfWork(c), build.actor, observed.bundle)
    if not observed.bundle.passed():
        return None
    with psycopg.connect(build.task["dsn"]) as c:
        version = c.execute("SELECT row_version FROM panestria.task WHERE id=%s", (task,)).fetchone()[0]
        submission = HandoffSubmission(
            handoff_id=str(uuid4()),
            plan_id=plan.plan_id,
            task_id=task,
            expected_task_version=version,
            evidence_sha256=digest,
        )
        return PlanStore().handoff(UnitOfWork(c), build.actor, submission, build.service)


@pytest.mark.parametrize("build", [PATHS], indirect=True)
def test_actual_node_checks_and_handoffs_unlock_final_node_without_completing_goal(build, tmp_path):
    plan = accepted(build)
    first, second = claim(build, plan), claim(build, plan)
    assert isinstance(first, Scheduled) and isinstance(second, Scheduled)
    handoff = verified_handoff(build, plan, first, build.candidate, tmp_path / "node-one")
    assert handoff is not None
    with psycopg.connect(build.task["dsn"]) as c:
        Scheduler().complete_node(
            UnitOfWork(c), build.actor, plan.plan_id, handoff.submission.handoff_id, build.service
        )
    with psycopg.connect(build.task["dsn"]) as c:
        Scheduler().complete_node(
            UnitOfWork(c), build.actor, plan.plan_id, handoff.submission.handoff_id, build.service
        )
    assert not isinstance(claim(build, plan), Scheduled)  # One passed sibling cannot satisfy both dependencies.
    _git(build.source, "checkout", "-b", "worker-two", build.base)
    (build.source / "part1.txt").write_text("second worker")
    _git(build.source, "add", "part1.txt")
    _git(build.source, "commit", "-m", "synthetic independent second node")
    candidate = _git(build.source, "rev-parse", "HEAD")
    _git(build.bare, "fetch", str(build.source), "worker-two")
    handoff2 = verified_handoff(build, plan, second, candidate, tmp_path / "node-two")
    assert handoff2 is not None
    with psycopg.connect(build.task["dsn"]) as c:
        Scheduler().complete_node(
            UnitOfWork(c), build.actor, plan.plan_id, handoff2.submission.handoff_id, build.service
        )
        assert c.execute("SELECT status FROM panestria.goal WHERE id=%s", (plan.goal_id,)).fetchone() == ("ACTIVE",)
        assert c.execute(
            "SELECT count(*) FROM panestria.approval_request WHERE goal_id=%s", (plan.goal_id,)
        ).fetchone() == (0,)
    final = claim(build, plan)
    assert isinstance(final, Scheduled) and final.lease.task_id == plan.nodes[-1].task_id
    with psycopg.connect(build.task["dsn"]) as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.task_event WHERE kind='build.scheduler.node_completed'"
        ).fetchone() == (2,)
        with pytest.raises(psycopg.Error), c.transaction():
            c.execute(
                "UPDATE panestria.build_worker_claim SET released_at=NULL,handoff_id=NULL WHERE released_at IS NOT NULL"
            )


@pytest.mark.parametrize("build", [PATHS], indirect=True)
def test_failed_node_keeps_dependents_blocked_and_does_not_forge_handoff(build, tmp_path):
    plan = accepted(build)
    first, second = claim(build, plan), claim(build, plan)
    assert isinstance(first, Scheduled) and isinstance(second, Scheduled)
    # The first node owns answer.txt. A candidate with that diff fails node two's part1.txt scope.
    assert verified_handoff(build, plan, second, build.candidate, tmp_path / "failed-node") is None
    queued = claim(build, plan)
    assert not isinstance(queued, Scheduled) and queued[-1].reason == "dependency_not_verified"
    with psycopg.connect(build.task["dsn"]) as c:
        assert c.execute("SELECT state FROM panestria.task WHERE id=%s", (second.lease.task_id,)).fetchone() == (
            "FAILED",
        )
        assert c.execute("SELECT count(*) FROM panestria.build_handoff").fetchone() == (0,)
        assert c.execute("SELECT count(*) FROM panestria.build_worker_claim WHERE released_at IS NULL").fetchone() == (
            2,
        )


@pytest.mark.parametrize("build", [PATHS], indirect=True)
def test_plan_consent_does_not_replace_owner_edit_consent(build):
    plan = accepted(build, edit_grant=False)
    queued = claim(build, plan)
    assert not isinstance(queued, Scheduled)
    assert queued[0].reason == "current_edit_policy_denied"
    with psycopg.connect(build.task["dsn"]) as c:
        assert c.execute("SELECT count(*) FROM panestria.build_worker_claim").fetchone() == (0,)
