"""Real canonical model admission/replay/crash limits; explicit generation/native fixtures."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_local_build_repair import local
from test_native_plan_execution import native_plan as native_plan  # noqa: F401
from test_native_plan_execution import owner_cli as owner_cli  # noqa: F401
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401
from test_plan_revisions import failed, fresh, returned
from typer.testing import CliRunner

from panestria.cli.main import app
from panestria.execution.local_repair import LocalBuildRepair
from panestria.kernel.errors import KernelDenied
from panestria.kernel.plan_revisions import PlanRevisionService
from panestria.kernel.repair_intents import repair_ledger
from panestria.kernel.uow import UnitOfWork


@pytest.mark.parametrize("prepared_plan", [{"wall_seconds": 1800}], indirect=True)
def test_concurrent_different_directories_replay_and_finite_turns_preserve_canonical_budget(native_plan, tmp_path):
    owner, _, parent, _, claims = failed(native_plan)
    proof = returned(owner, parent, claims)
    repair, model = local(owner, tmp_path)
    entered, release = threading.Event(), threading.Event()

    def block():
        entered.set()
        assert release.wait(6)

    model.after = block
    first_dir = tmp_path / "first"
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            repair.propose,
            parent.proposal.plan_id,
            parent.proposal.sha256(),
            proof,
            first_dir,
            local_model_run=True,
            idempotency_key="first",
        )
        assert entered.wait(5)
        try:
            # A second process/instance and fresh directory/key do not bypass an
            # acknowledged unresolved intent. No native/edit/resource claim is made.
            other = LocalBuildRepair(owner, repair.planner.settings, repair.planner.model)
            with pytest.raises(KernelDenied, match="repair_draft_prior_unconfirmed"):
                other.propose(
                    parent.proposal.plan_id,
                    parent.proposal.sha256(),
                    proof,
                    tmp_path / "racing",
                    local_model_run=True,
                    idempotency_key="racing",
                )
            assert len(model.calls) == 1 and not (tmp_path / "racing").exists()
            assert owner.progress(parent.proposal.goal_id)["repair"]["unconfirmed_planning_turns"] == 1
        finally:
            release.set()
        first = future.result(timeout=10)
    model.after = None
    replay = LocalBuildRepair(owner, repair.planner.settings, repair.planner.model).propose(
        parent.proposal.plan_id,
        parent.proposal.sha256(),
        proof,
        first_dir,
        local_model_run=True,
        idempotency_key="first",
    )
    assert replay["replayed"] and replay["proposal_sha256"] == first["proposal_sha256"] and len(model.calls) == 1
    second = repair.propose(
        parent.proposal.plan_id,
        parent.proposal.sha256(),
        proof,
        tmp_path / "second",
        local_model_run=True,
        idempotency_key="second",
    )
    assert second["status"] == "VALIDATED_DRAFT" and len(model.calls) == 2
    with pytest.raises(KernelDenied, match="repair_model_turn_limit_exhausted"):
        repair.propose(
            parent.proposal.plan_id,
            parent.proposal.sha256(),
            proof,
            tmp_path / "third",
            local_model_run=True,
            idempotency_key="third",
        )
    assert len(model.calls) == 2 and not (tmp_path / "third").exists()
    with owner.connect() as c:
        ledger = repair_ledger(UnitOfWork(c), owner.actor, parent.proposal.goal_id)
        assert len(ledger.intents) == len(ledger.outcomes) == 2 and not ledger.unresolved
        assert ledger.charged_wall_seconds == 720
        assert c.execute(
            "SELECT count(*) FROM panestria.build_plan WHERE goal_id=%s", (parent.proposal.goal_id,)
        ).fetchone() == (1,)
    # A missing/edited local export cannot be silently replaced or blessed by
    # replay; immutable protected bytes remain available as original evidence.
    (first_dir / "proposal.json").write_text("{}")
    with pytest.raises(KernelDenied, match="repair_draft_files_unconfirmed"):
        repair.propose(
            parent.proposal.plan_id,
            parent.proposal.sha256(),
            proof,
            first_dir,
            local_model_run=True,
            idempotency_key="first",
        )
    assert len(model.calls) == 2


@pytest.mark.parametrize("prepared_plan", [{"wall_seconds": 1800}], indirect=True)
def test_unknown_return_is_durable_and_blocks_new_key_revision_and_false_completion(native_plan, tmp_path):
    owner, _, parent, _, claims = failed(native_plan)
    proof = returned(owner, parent, claims)
    repair, model = local(owner, tmp_path)
    output = tmp_path / "interrupted"

    def lost_return():
        raise RuntimeError("FIXTURE ambiguous model return; no actual inference")

    model.after = lost_return
    with pytest.raises(RuntimeError, match="FIXTURE ambiguous"):
        repair.propose(
            parent.proposal.plan_id,
            parent.proposal.sha256(),
            proof,
            output,
            local_model_run=True,
            idempotency_key="interrupted",
        )
    assert len(model.calls) == 1
    replay = repair.propose(
        parent.proposal.plan_id,
        parent.proposal.sha256(),
        proof,
        output,
        local_model_run=True,
        idempotency_key="interrupted",
    )
    assert replay["status"] == "UNCONFIRMED" and replay["physical_return"] == "UNCONFIRMED"
    with pytest.raises(KernelDenied, match="repair_draft_prior_unconfirmed"):
        repair.propose(
            parent.proposal.plan_id,
            parent.proposal.sha256(),
            proof,
            tmp_path / "new-key",
            local_model_run=True,
            idempotency_key="new-key",
        )
    with owner.connect() as c:
        with pytest.raises(KernelDenied, match="plan_previous_work_unconfirmed"):
            PlanRevisionService().propose(
                UnitOfWork(c),
                owner.actor,
                parent.proposal.plan_id,
                parent.proposal.sha256(),
                fresh(parent.proposal),
                parent.inventory,
                proof,
            )
    progress = owner.progress(parent.proposal.goal_id)
    assert progress["attention_reason"] == "RECONCILIATION_REQUIRED"
    assert progress["repair"]["unconfirmed_planning_turns"] == 1
    assert progress["repair"]["wall_envelope_charged_seconds"] == 630
    assert progress["release_acceptance"] == "NOT_ASSESSED" and progress["goal_status"] == "ACTIVE"
    build = tmp_path / "inspect-build.json"
    build.write_text(owner.settings.model_dump_json())
    build.chmod(0o600)
    result = CliRunner().invoke(app, ["plan", "repair-turns", parent.proposal.goal_id, "--config", str(build)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["turns"][0]["status"] == "UNCONFIRMED"
    assert "FIXTURE ambiguous" not in result.output and len(model.calls) == 1
