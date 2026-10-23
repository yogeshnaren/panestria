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
from schema_support import current_schema_revision


@pytest.mark.parametrize("prepared_plan", [{"wall_seconds": 1800}], indirect=True)
def test_concurrent_different_directories_replay_and_finite_turns_preserve_canonical_budget(
    native_plan, tmp_path, monkeypatch
):
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
    import panestria.execution.local_repair as implementation

    original_finish = implementation.finish_repair

    def lost_ack(uow, actor, goal, outcome):
        original_finish(uow, actor, goal, outcome)
        uow.connection.commit()  # Actual commit; only its acknowledgment is lost.
        raise OSError("FIXTURE lost outcome commit acknowledgment")

    monkeypatch.setattr(implementation, "finish_repair", lost_ack)
    with pytest.raises(OSError, match="FIXTURE lost outcome"):
        repair.propose(
            parent.proposal.plan_id,
            parent.proposal.sha256(),
            proof,
            tmp_path / "second",
            local_model_run=True,
            idempotency_key="second",
        )
    monkeypatch.setattr(implementation, "finish_repair", original_finish)
    second = repair.propose(
        parent.proposal.plan_id,
        parent.proposal.sha256(),
        proof,
        tmp_path / "second",
        local_model_run=True,
        idempotency_key="second",
    )
    assert second["status"] == "VALIDATED_DRAFT" and second["replayed"] and len(model.calls) == 2
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


@pytest.mark.parametrize("prepared_plan", [{"wall_seconds": 1800}], indirect=True)
def test_unknown_repair_backup_restore_preserves_charges_unique_slots_and_refuses_audit_downgrade(
    native_plan, tmp_path, record_property
):
    import hashlib
    import os
    import subprocess
    import sys
    from pathlib import Path
    from uuid import uuid4

    import psycopg
    from psycopg import sql
    from test_memory_restore import _fixture_container

    from panestria.contracts.repair_intent import FINISHED, STARTED
    from panestria.execution.owner_build import OwnerBuild
    from panestria.kernel.repositories.tasks import append_event

    owner, _, parent, _, claims = failed(native_plan)
    proof = returned(owner, parent, claims)
    repair, model = local(owner, tmp_path)

    def interrupted():
        raise RuntimeError("FIXTURE process return unknown")

    model.after = interrupted
    output = tmp_path / "unknown"
    with pytest.raises(RuntimeError, match="FIXTURE process return"):
        repair.propose(
            parent.proposal.plan_id,
            parent.proposal.sha256(),
            proof,
            output,
            local_model_run=True,
            idempotency_key="unknown",
        )
    container = _fixture_container()
    dump = subprocess.run(
        ["docker", "exec", container, "pg_dump", "-U", "panestria_synthetic", "-d", owner.dsn.rsplit("/", 1)[1], "-Fc"],
        capture_output=True,
        check=True,
        timeout=30,
    )
    record_property("backup_sha256", hashlib.sha256(dump.stdout).hexdigest())
    name = "panestria_repair_restore_" + uuid4().hex
    restored = owner.dsn.rsplit("/", 1)[0] + "/" + name
    with psycopg.connect(owner.dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            subprocess.run(
                ["docker", "exec", "-i", container, "pg_restore", "-U", "panestria_synthetic", "-d", name],
                input=dump.stdout,
                capture_output=True,
                check=True,
                timeout=30,
            )
            recovered = LocalBuildRepair(
                OwnerBuild(owner.settings, restored), repair.planner.settings, repair.planner.model
            )
            replay = recovered.propose(
                parent.proposal.plan_id,
                parent.proposal.sha256(),
                proof,
                output,
                local_model_run=True,
                idempotency_key="unknown",
            )
            assert replay["status"] == "UNCONFIRMED" and len(model.calls) == 1
            with psycopg.connect(restored) as c:
                ledger = repair_ledger(UnitOfWork(c), owner.actor, parent.proposal.goal_id)
                assert ledger.charged_wall_seconds == 360 and ledger.unresolved == 1
                original = ledger.intents[0].model_dump(mode="json")
                # The real restored indexes reject duplicates even when a caller
                # bypasses the application projection. Every rejected insert rolls back.
                for payload, constraint in [
                    ({**original, "draft_id": str(uuid4()), "key_sha256": "ab" * 32}, "repair_draft_turn_once"),
                    ({**original, "draft_id": str(uuid4()), "turn": 2}, "repair_draft_key_once"),
                ]:
                    with pytest.raises(psycopg.errors.UniqueViolation) as error, c.transaction():
                        append_event(
                            UnitOfWork(c),
                            goal_id=parent.proposal.goal_id,
                            task_id=None,
                            actor=owner.actor.owner_id,
                            kind=STARTED,
                            payload=payload,
                        )
                    assert error.value.diag.constraint_name == constraint
                with pytest.raises(psycopg.errors.UniqueViolation) as error, c.transaction():
                    append_event(
                        UnitOfWork(c),
                        goal_id=parent.proposal.goal_id,
                        task_id=None,
                        actor=owner.actor.owner_id,
                        kind=FINISHED,
                        payload=ledger.outcomes[0].model_dump(mode="json"),
                    )
                assert error.value.diag.constraint_name == "repair_draft_outcome_once"
                assert repair_ledger(UnitOfWork(c), owner.actor, parent.proposal.goal_id) == ledger
            refused = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "alembic",
                    "-c",
                    "migrations/alembic.ini",
                    "downgrade",
                    "0036_returned_build_release",
                ],
                cwd=Path(__file__).resolve().parents[2],
                env={**os.environ, "PANESTRIA_DATABASE_URL": restored},
                capture_output=True,
                timeout=30,
            )
            assert refused.returncode != 0 and b"repair I/O audit exists" in refused.stderr
            with psycopg.connect(restored) as c:
                assert c.execute("SELECT version_num FROM alembic_version").fetchone() == (current_schema_revision(),)
                assert repair_ledger(UnitOfWork(c), owner.actor, parent.proposal.goal_id) == ledger
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
