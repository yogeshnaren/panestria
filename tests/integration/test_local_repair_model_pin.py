"""Real repair intent/outcome persistence with explicit generation/native fixtures."""

import json
from dataclasses import replace

import pytest
from test_local_build_repair import local
from test_native_plan_execution import native_plan as native_plan  # noqa: F401
from test_native_plan_execution import owner_cli as owner_cli  # noqa: F401
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401
from test_plan_revisions import failed, returned

from model_manifest_support import model_manifest
from panestria.execution.local_repair import LocalBuildRepair
from panestria.kernel.repair_intents import repair_ledger
from panestria.kernel.uow import UnitOfWork


@pytest.mark.parametrize("prepared_plan", [{"wall_seconds": 1800}], indirect=True)
def test_manifest_pin_is_in_acknowledged_repair_intent_and_replay_keeps_original(
    native_plan, tmp_path, record_property,
):
    owner, _, parent, _, claims = failed(native_plan)
    proof = returned(owner, parent, claims)
    prior, model = local(owner, tmp_path)
    selected = model_manifest().for_json_output()
    expected = tmp_path / "expected.json"
    expected.write_text(selected.model_dump_json())
    expected.chmod(0o600)
    settings = prior.planner.settings.model_copy(update={"model_manifest_file": expected})
    seen = []

    class BoundModel:
        def generate(self, request):
            with owner.connect() as c:
                ledger = repair_ledger(UnitOfWork(c), owner.actor, parent.proposal.goal_id)
                assert len(ledger.intents) == 1 and ledger.intents[0].request_sha256 == request.sha256()
            assert request.model_manifest_sha256 == selected.sha256()
            seen.append(request)
            return replace(model.generate(request), model_manifest_sha256=selected.sha256())

    repair = LocalBuildRepair(owner, settings, BoundModel())
    output = tmp_path / "bound-draft"
    args = (parent.proposal.plan_id, parent.proposal.sha256(), proof, output)
    result = repair.propose(*args, local_model_run=True, idempotency_key="manifest")
    assert result["status"] == "VALIDATED_DRAFT" and len(seen) == 1
    assert json.loads((output / "result.json").read_bytes())["model_manifest"] == selected.model_dump(mode="json")
    expected.write_text(model_manifest(template_sha256="9" * 64).for_json_output().model_dump_json())
    replay = LocalBuildRepair(owner, settings, BoundModel()).propose(
        *args, local_model_run=True, idempotency_key="manifest",
    )
    assert replay["replayed"] and replay["proposal_sha256"] == result["proposal_sha256"] and len(seen) == 1
    assert json.loads((output / "result.json").read_bytes())["model_manifest"] == selected.model_dump(mode="json")
    with owner.connect() as c:
        ledger = repair_ledger(UnitOfWork(c), owner.actor, parent.proposal.goal_id)
        assert len(ledger.intents) == len(ledger.outcomes) == 1 and ledger.charged_wall_seconds == 360
    record_property("execution_mode", "ACTUAL_PG_REPAIR_LEDGER_FILES__EXPLICIT_MODEL_NATIVE_RUNTIME_FIXTURES")
