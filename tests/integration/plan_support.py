"""Shared real Postgres/Git/CAS plan fixtures; synthetic capacity and worker identities."""

from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest

from panestria.contracts.goal import contract_sha256, load_contract
from panestria.contracts.hardware import HardwareManifest
from panestria.contracts.plan import HandoffSubmission, PlanNode, PlanProposal, ProjectInventory, WorkerInventory
from panestria.kernel.plan_scope import task_plan_scope
from panestria.kernel.plan_store import PlanStore
from panestria.kernel.policy import PolicyService
from panestria.kernel.scheduler import Scheduler
from panestria.kernel.uow import UnitOfWork
from panestria.resources.hardware import PROBE_SHA256
from panestria.verification.build import verify_build
from panestria.verification.git_snapshot import materialize

PATHS = ("answer.txt", *(f"part{i}.txt" for i in range(1, 8)))


@pytest.fixture
def r1_task(r1_migration_task):
    return r1_migration_task


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


def accepted(build, count=2, *, overlap=False, edit_grant=True, base_snapshot_sha=None):
    if edit_grant:
        reviewed_edit_policy(build)
    inventory = ProjectInventory(
        owner_id=build.actor.owner_id,
        project_id=build.actor.project_id,
        base_commit=build.base,
        snapshot_sha256=base_snapshot_sha or build.snapshot.manifest_sha256,
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
