"""Canonical stopped Build to local repair draft/review/merge; explicit model/native fixtures."""

import json
from types import SimpleNamespace
from uuid import UUID

import pytest
from test_native_plan_execution import native_plan as native_plan  # noqa: F401
from test_native_plan_execution import owner_cli as owner_cli  # noqa: F401
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401
from test_plan_revisions import failed, returned

from panestria.config_plan import PlanModelSettings
from panestria.contracts.inference import InferenceResult, Usage
from panestria.contracts.plan import PlanProposal
from panestria.execution.local_repair import LocalBuildRepair
from panestria.inference.runtime import MODEL
from panestria.kernel.errors import KernelDenied
from panestria.kernel.plan_revisions import PlanRevisionService
from panestria.kernel.plan_store import PlanStore
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.uow import UnitOfWork


def local(owner, tmp_path):
    cache = tmp_path / "fixture-cache"
    cache.mkdir(mode=0o700)
    for name in ("blobs", "manifests"):
        (cache / name).mkdir()
    settings = PlanModelSettings(
        schema_version=1,
        owner_id=UUID(owner.actor.owner_id),
        project_id=UUID(owner.actor.project_id),
        model_cache=cache,
        runtime_directory=tmp_path / "fixture-runtime",
    )
    state = SimpleNamespace(calls=[], after=None, wall=90)

    class ModelFixture:
        def generate(self, request):
            state.calls.append(request)
            if state.after:
                state.after()
            return InferenceResult(
                MODEL,
                json.dumps(
                    {
                        "edits": [
                            {
                                "task_id": name,
                                "worker_ref": "claude-public-bash",
                                "capabilities": ["scoped-bash"],
                                "paths": [path],
                                "acceptance_keys": ["paths"],
                                "wall_seconds_per_attempt": state.wall,
                            }
                            for name, path in [("repair-one", "calculator.py"), ("repair-two", "notes/build.txt")]
                        ]
                    }
                ),
                Usage(120, 150),
                0.1,
                None,
                finish_reason="stop",
            )

    return LocalBuildRepair(owner, settings, ModelFixture()), state


@pytest.mark.parametrize("prepared_plan", [{"wall_seconds": 900}], indirect=True)
def test_released_failure_drafts_one_bounded_repair_then_requires_exact_revision_review(
    native_plan, tmp_path, monkeypatch
):
    owner, runner, parent, native, claims = failed(native_plan)
    proof = returned(owner, parent, claims)
    repair, model = local(owner, tmp_path)
    output = tmp_path / "repair"
    with owner.connect() as c:
        before = c.execute("SELECT count(*) FROM panestria.task_event").fetchone()
    with pytest.raises(KernelDenied, match="explicit_local_plan_model_intent_required"):
        repair.propose(parent.proposal.plan_id, parent.proposal.sha256(), proof, output)
    assert not output.exists() and not model.calls
    from typer.testing import CliRunner

    from panestria.cli.main import app
    from panestria.execution.local_plan import LocalPlanModel

    model_path, build_path = tmp_path / "model.json", tmp_path / "build.json"
    for path, value in [(model_path, repair.planner.settings), (build_path, owner.settings)]:
        path.write_text(value.model_dump_json())
        path.chmod(0o600)
    monkeypatch.setenv("PANESTRIA_DATABASE_URL", owner.dsn)
    monkeypatch.setattr(LocalPlanModel, "generate", lambda _self, request: repair.planner.model.generate(request))
    cli = CliRunner().invoke(
        app,
        [
            "plan",
            "propose-repair",
            parent.proposal.plan_id,
            parent.proposal.sha256(),
            proof,
            "--build-config",
            str(build_path),
            "--model-config",
            str(model_path),
            "--output-directory",
            str(output),
            "--local-model-run",
        ],
    )
    assert cli.exit_code == 0, cli.output
    receipt = json.loads(cli.stdout)
    assert receipt["status"] == "VALIDATED_DRAFT" and receipt["execution_authority"] == "NONE"
    assert len(model.calls) == 1 and model.calls[0].offline
    context = json.loads((output / "repair-context.json").read_text())
    assert context["remaining_wall_seconds"] == 630 and len(context["failure_states"]) == 2
    assert '"edits_wall_budget":540' in model.calls[0].prompt
    assert receipt["repair_context_sha256"] and receipt["canonical_plan_state"] == "NOT_STAGED"
    proposal = PlanProposal.model_validate_json((output / "proposal.json").read_bytes())
    assert proposal.contract_sha256 == parent.proposal.contract_sha256 and len(proposal.nodes) == 3
    with owner.connect() as c:
        assert c.execute("SELECT count(*) FROM panestria.task_event").fetchone() == before
        assert c.execute(
            "SELECT count(*) FROM panestria.build_plan WHERE goal_id=%s", (proposal.goal_id,)
        ).fetchone() == (1,)
    with pytest.raises(KernelDenied, match="fresh_private_plan_output_required"):
        repair.propose(parent.proposal.plan_id, parent.proposal.sha256(), proof, output, local_model_run=True)
    assert len(model.calls) == 1
    with owner.connect() as c:
        revision = PlanRevisionService().propose(
            UnitOfWork(c),
            owner.actor,
            parent.proposal.plan_id,
            parent.proposal.sha256(),
            proposal,
            parent.inventory,
            proof,
        )
    assert revision.state == "PROPOSED" and revision.consent.cumulative_wall_seconds == 540
    with pytest.raises(KernelDenied, match="plan_not_accepted"):
        runner.run(proposal.plan_id, public_subscription_run=True)
    with owner.connect() as c:
        PlanStore().accept(UnitOfWork(c), owner.actor, proposal.plan_id, revision.effect_digest, accept_plan=True)
    native["unavailable"] = False
    assert runner.run(proposal.plan_id, public_subscription_run=True)["status"] == "WAITING_APPROVAL"
    status = owner.status(proposal.goal_id)
    approval = status["approval"]
    assert (
        owner.approve(
            approval["approval_id"], approval["effect_digest"], approval["expected_version"], "repair-test-owner"
        )["task_state"]
        == "COMPLETED"
    )


@pytest.mark.parametrize("prepared_plan", [{"wall_seconds": 900}], indirect=True)
def test_unknown_work_overbudget_output_and_changed_source_stop_without_automatic_retry(native_plan, tmp_path):
    owner, _, parent, _, claims = failed(native_plan)
    proof = returned(owner, parent, claims[:1])
    repair, model = local(owner, tmp_path)
    with pytest.raises(KernelDenied, match="plan_previous_work_unconfirmed"):
        repair.propose(
            parent.proposal.plan_id, parent.proposal.sha256(), proof, tmp_path / "held", local_model_run=True
        )
    assert not model.calls and not (tmp_path / "held").exists()
    proof = returned(owner, parent, claims[1:])
    model.wall = 300  # Valid under900 original, but690 including final exceeds630 remaining.
    over = tmp_path / "over"
    with pytest.raises(KernelDenied, match="local_plan_remaining_budget_exceeded"):
        repair.propose(parent.proposal.plan_id, parent.proposal.sha256(), proof, over, local_model_run=True)
    assert len(model.calls) == 1 and not (over / "proposal.json").exists()
    assert json.loads((over / "result.json").read_text())["status"] == "UNAVAILABLE"
    model.wall = 90

    def source_changed():
        with owner.connect() as c:
            append_event(
                UnitOfWork(c),
                goal_id=parent.proposal.goal_id,
                task_id=None,
                actor=owner.actor.owner_id,
                kind="fixture.owner.observation",
                payload={"fixture_only": True},
            )

    model.after = source_changed
    changed = tmp_path / "changed"
    with pytest.raises(KernelDenied, match="local_repair_source_changed"):
        repair.propose(parent.proposal.plan_id, parent.proposal.sha256(), proof, changed, local_model_run=True)
    assert len(model.calls) == 2 and not (changed / "proposal.json").exists()
    assert (changed / "response.txt").is_file()
    assert json.loads((changed / "result.json").read_text())["status"] == "UNAVAILABLE"
    assert json.loads((changed / "result.json").read_text())["automatic_retry"] is False
    with owner.connect() as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.build_plan WHERE goal_id=%s", (parent.proposal.goal_id,)
        ).fetchone() == (1,)
