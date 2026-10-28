"""Actual atomic PG goal/check/proposal staging and owner acceptance; no worker calls."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest
from build_support import build as build  # noqa: F401
from plan_support import PATHS, capacity, reviewed_edit_policy
from plan_support import r1_task as r1_task  # noqa: F401
from typer.testing import CliRunner

from panestria.cli.main import app
from panestria.contracts.goal import contract_sha256, load_contract
from panestria.contracts.plan import PlanNode, PlanProposal, ProjectInventory, WorkerInventory
from panestria.kernel.errors import KernelDenied
from panestria.kernel.plan_store import PlanStore
from panestria.kernel.plan_submission import PlanSubmissionService
from panestria.kernel.scheduler import Scheduled, Scheduler
from panestria.kernel.uow import UnitOfWork
from panestria.verification.git_snapshot import materialize


@pytest.fixture
def submission(build, tmp_path):
    reviewed_edit_policy(build)
    document = build.contract.model_dump(mode="json")
    document.update(goal_id=str(uuid4()), contract_version=1, privacy_class="PUBLIC")
    contract = load_contract(document)
    snapshot = materialize(build.bare, build.base, build.base, tmp_path / "inventory-source")
    inventory = ProjectInventory(
        owner_id=build.actor.owner_id,
        project_id=build.actor.project_id,
        base_commit=build.base,
        snapshot_sha256=snapshot.manifest_sha256,
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
    first, last = str(uuid4()), str(uuid4())
    nodes = tuple(
        PlanNode(
            task_id=t,
            depends_on=() if i == 0 else (first,),
            worker_ref="synthetic-controller-fixture",
            capabilities=("scoped-file-edit",),
            paths=("answer.txt",),
            acceptance_keys=("AC-002",) if i == 0 else tuple(c.id for c in contract.acceptance),
            expected_artifacts=("patch",),
            attempts=1,
            wall_seconds_per_attempt=30,
            api_microusd_per_attempt=0,
        )
        for i, t in enumerate((first, last))
    )
    proposal = PlanProposal(
        plan_id=str(uuid4()),
        owner_id=build.actor.owner_id,
        project_id=build.actor.project_id,
        goal_id=contract.goal_id,
        contract_sha256=contract_sha256(contract),
        inventory_sha256=inventory.sha256(),
        privacy_class="PUBLIC",
        nodes=nodes,
    )
    return build, document, proposal, inventory


def stage(f):
    build, document, proposal, inventory = f
    with psycopg.connect(build.task["dsn"]) as c:
        return PlanSubmissionService().stage(
            UnitOfWork(c), build.actor, document, proposal, inventory, "owner-plan-stage"
        )


@pytest.mark.parametrize("build", [PATHS], indirect=True)
def test_concurrent_stage_creates_one_goal_checkset_and_proposal_before_separate_owner_acceptance(submission):
    build, _, proposal, _ = submission
    barrier = Barrier(2)

    def one():
        barrier.wait(timeout=5)
        return stage(submission)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [f.result(timeout=15) for f in [pool.submit(one), pool.submit(one)]]
    assert {r.effect_digest for r in results} == {results[0].effect_digest}
    assert {r.replayed for r in results} == {False, True}
    assert all(r.state == "PROPOSED" and r.execution_authority == "NONE" for r in results)
    with psycopg.connect(build.task["dsn"]) as c:
        assert c.execute("SELECT count(*) FROM panestria.task WHERE goal_id=%s", (proposal.goal_id,)).fetchone() == (0,)
        assert c.execute(
            "SELECT count(*) FROM panestria.acceptance_check a "
            "JOIN panestria.goal_contract g ON g.id=a.contract_id WHERE g.goal_id=%s",
            (proposal.goal_id,),
        ).fetchone() == (3,)
        assert c.execute("SELECT status FROM panestria.goal WHERE id=%s", (proposal.goal_id,)).fetchone() == (
            "CREATED",
        )
        PlanStore().accept(UnitOfWork(c), build.actor, proposal.plan_id, results[0].effect_digest, accept_plan=True)
    assert stage(submission).state == "ACCEPTED"  # Replay does not allocate another task/attempt or consent.
    with psycopg.connect(build.task["dsn"]) as c:
        assert (
            c.execute("SELECT state FROM panestria.task WHERE goal_id=%s", (proposal.goal_id,)).fetchall()
            == [("CREATED",)] * 2
        )
        claimed = Scheduler().claim_ready(UnitOfWork(c), build.actor, proposal.plan_id, capacity(), build.service)
        assert isinstance(claimed, Scheduled)
        assert c.execute("SELECT status FROM panestria.goal WHERE id=%s", (proposal.goal_id,)).fetchone() == ("ACTIVE",)
        assert c.execute(
            "SELECT count(*) FROM panestria.worker_invocation WHERE task_id=%s", (claimed.lease.task_id,)
        ).fetchone() == (0,)


@pytest.mark.parametrize("build", [PATHS], indirect=True)
def test_atomic_rollback_invalid_privacy_cash_and_replay_checkset_tampering_are_refused(submission):
    build, document, proposal, inventory = submission
    with psycopg.connect(build.task["dsn"]) as c:
        PlanSubmissionService().stage(UnitOfWork(c), build.actor, document, proposal, inventory, "owner-plan-stage")
        c.rollback()
        assert c.execute("SELECT count(*) FROM panestria.goal WHERE id=%s", (proposal.goal_id,)).fetchone() == (0,)
    for changed in (
        {**document, "privacy_class": "RESTRICTED"},
        {**document, "budget": {**document["budget"], "max_api_usd": "1"}},
    ):
        with psycopg.connect(build.task["dsn"]) as c:
            with pytest.raises(KernelDenied, match="public_zero_cash_plan_required"), c.transaction():
                PlanSubmissionService().stage(UnitOfWork(c), build.actor, changed, proposal, inventory, "invalid-stage")
    stage(submission)
    with psycopg.connect(build.task["dsn"]) as c:
        c.execute(
            "UPDATE panestria.acceptance_check SET description='synthetic tamper' WHERE contract_id IN "
            "(SELECT id FROM panestria.goal_contract WHERE goal_id=%s)",
            (proposal.goal_id,),
        )
    with pytest.raises(KernelDenied, match="plan_submission_checks_changed"):
        stage(submission)
    with psycopg.connect(build.task["dsn"]) as c:
        assert c.execute("SELECT count(*) FROM panestria.task WHERE goal_id=%s", (proposal.goal_id,)).fetchone() == (0,)


@pytest.mark.parametrize("build", [PATHS], indirect=True)
def test_owner_cli_stages_private_files_without_launch_or_task_acceptance(submission, tmp_path, monkeypatch):
    build, document, proposal, inventory = submission
    for name, data in (
        ("contract", json.dumps(document)),
        ("proposal", proposal.model_dump_json()),
        ("inventory", inventory.model_dump_json()),
    ):
        path = tmp_path / (name + ".json")
        path.write_text(data)
        path.chmod(0o600)
    monkeypatch.setenv("PANESTRIA_DATABASE_URL", build.task["dsn"])
    result = CliRunner().invoke(
        app,
        [
            "plan",
            "stage",
            build.actor.owner_id,
            build.actor.project_id,
            "--contract",
            str(tmp_path / "contract.json"),
            "--proposal",
            str(tmp_path / "proposal.json"),
            "--inventory",
            str(tmp_path / "inventory.json"),
            "--idempotency-key",
            "cli-stage",
        ],
    )
    assert result.exit_code == 0, result.exception
    assert json.loads(result.stdout)["state"] == "PROPOSED"
    with psycopg.connect(build.task["dsn"]) as c:
        assert c.execute("SELECT count(*) FROM panestria.task WHERE goal_id=%s", (proposal.goal_id,)).fetchone() == (0,)
        assert c.execute(
            "SELECT count(*) FROM panestria.build_plan_acceptance WHERE plan_id=%s", (proposal.plan_id,)
        ).fetchone() == (0,)
