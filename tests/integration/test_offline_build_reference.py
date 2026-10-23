"""Actual canonical merge/private archive/offline restore; native/auth are fixtures."""

import json
import shutil
from dataclasses import replace
from itertools import count
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_native_plan_execution import native_plan as native_plan  # noqa: F401
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401
from test_owner_build_cli import invoke
from test_owner_build_cli import owner_cli as owner_cli  # noqa: F401
from test_registered_check_authority import git
from typer.testing import CliRunner

from panestria.brokers.harness.claude_build import ClaudeScopedBashAdapter
from panestria.brokers.harness.event_parser import ClaudeEventParser
from panestria.cli.main import app
from panestria.contracts.offline_result import OfflineBuildReference
from panestria.execution.offline_build import read_reference
from panestria.kernel.build import BuildEvidenceStore
from panestria.kernel.errors import KernelDenied


def enable_capture(owner, f):
    cfg = json.loads(f.config.read_text())
    cfg["capture_verified_results"] = True
    f.config.write_text(json.dumps(cfg))
    owner.settings = owner.settings.model_copy(update={"capture_verified_results": True})


def approve(owner, goal):
    a = owner.status(goal)["approval"]
    return owner.approve(a["approval_id"], a["effect_digest"], a["expected_version"], "offline-reference-owner")


def test_actual_confirmed_build_reference_is_portable_offline_and_not_training_consent(
    native_plan, prepared_plan, tmp_path, monkeypatch
):
    f, owner, _, plan = prepared_plan
    _, runner, _, state = native_plan
    assert owner.settings.capture_verified_results is False
    enable_capture(owner, f)
    # Feed synthetic init/result through the actual parser, then retain the
    # observation through the actual canonical receipt and capture path. This
    # is protocol/capture evidence, never live Claude model qualification.
    original = ClaudeScopedBashAdapter.build_public
    calls = count()

    def observed(adapter, *args, **kwargs):
        observation = original(adapter, *args, **kwargs)
        if next(calls) == 0:
            return observation  # Legacy receipt: no recorded requested/reported model.
        parser = ClaudeEventParser()
        for body in (
            {"type": "system", "subtype": "init", "session_id": "synthetic", "model": "claude-haiku-4-5-20251001"},
            {"type": "result", "subtype": "success", "is_error": False, "result": "synthetic"},
        ):
            parser.feed(json.dumps(body).encode() + b"\n")
        return replace(
            observation,
            requested_model="haiku",
            process=replace(observation.process, result=parser.finish(0)),
        )

    monkeypatch.setattr(ClaudeScopedBashAdapter, "build_public", observed)
    assert runner.run(plan.plan_id, public_subscription_run=True)["status"] == "WAITING_APPROVAL"
    with pytest.raises(KernelDenied, match="requires_confirmed_final_merge"):
        owner.capture_reference(plan.goal_id)
    assert not (f.root / "offline-results").exists()
    result = approve(owner, plan.goal_id)
    assert result["task_state"] == "COMPLETED" and result["offline_reference"]["status"] == "SAVED"
    digest = result["offline_reference"]["reference_sha256"]
    manifest = read_reference(f.root, owner.actor.owner_id, owner.actor.project_id, digest)
    assert manifest.permitted_purpose == "OWNER_LOCAL_REFERENCE" and manifest.training_eligibility == "UNKNOWN"
    assert manifest.training_export == "DENIED" and all(x.model is None for x in manifest.invocations)
    assert manifest.schema_version == 2
    assert all(x.request_sha256 and x.configuration_sha256 for x in manifest.invocations)
    observed_models = [x for x in manifest.invocations if x.reported_init_model is not None]
    assert len(observed_models) == 1
    assert all(
        x.requested_model == "haiku" and x.reported_init_model == "claude-haiku-4-5-20251001" for x in observed_models
    )
    assert all(x.requested_model is None for x in manifest.invocations if x not in observed_models)
    with owner.connect() as c:
        rows = c.execute(
            "SELECT binding FROM panestria.worker_invocation WHERE task_id IN "
            "(SELECT id FROM panestria.task WHERE goal_id=%s)",
            (plan.goal_id,),
        ).fetchall()
    assert {x.request_sha256 for x in manifest.invocations} == {r[0]["request_sha256"] for r in rows}
    assert {x.configuration_sha256 for x in manifest.invocations} == {r[0]["configuration_sha256"] for r in rows}
    assert len(manifest.invocations) == 5 and manifest.candidate_commit == git(f.bare, "rev-parse", "HEAD")
    assert manifest.validation == "INDEPENDENT_CHECKS_AND_CONFIRMED_MERGE"
    with owner.connect() as c:
        before = c.execute("SELECT count(*) FROM panestria.task_event").fetchone()
    files = set((f.root / "offline-results/blobs").iterdir())
    again = invoke(f, "capture-reference", plan.goal_id)
    assert again["reference_sha256"] == digest and set((f.root / "offline-results/blobs").iterdir()) == files
    with owner.connect() as c:
        assert c.execute("SELECT count(*) FROM panestria.task_event").fetchone() == before
    assert state["launches"] == 2
    with pytest.raises(KernelDenied, match="not_found"):
        read_reference(f.root, str(uuid4()), owner.actor.project_id, digest)
    # Portable self-contained reference without the source DB/Git/runtime/auth.
    restored = tmp_path / "restored"
    restored.mkdir(mode=0o700)
    shutil.copytree(f.root / "offline-results", restored / "offline-results")
    cfg = json.loads(f.config.read_text())
    cfg.update(root=str(restored), certificates="/ABSENT_CERTIFICATES", native_config="/ABSENT_AUTH")
    config = tmp_path / "restored.json"
    config.write_text(json.dumps(cfg))
    config.chmod(0o600)
    monkeypatch.setenv("PANESTRIA_DATABASE_URL", "NO_DATABASE_OR_CREDENTIAL_AVAILABLE")
    viewed = CliRunner().invoke(app, ["build", "reference", "--config", str(config), digest, "--diff"])
    assert viewed.exit_code == 0 and json.loads(viewed.stdout)["candidate_commit"] == manifest.candidate_commit
    assert "+value = 43" in json.loads(viewed.stdout)["diff"]
    assert "NO_DATABASE_OR_CREDENTIAL_AVAILABLE" not in viewed.stdout
    store = BuildEvidenceStore(restored / "offline-results/blobs")
    assert json.loads(viewed.stdout)["invocations"] == manifest.model_dump(mode="json")["invocations"]
    # Original v1 archives still read offline with UNKNOWN metadata. No repair,
    # current model/default lookup, DB connection or provider retry is involved.
    legacy = manifest.model_dump(mode="json")
    legacy["schema_version"] = 1
    with pytest.raises(ValidationError, match="legacy_reference_identity_must_remain_unknown"):
        OfflineBuildReference.model_validate_json(json.dumps(legacy))
    for invocation in legacy["invocations"]:
        for field in ("request_sha256", "configuration_sha256", "requested_model", "reported_init_model"):
            invocation.pop(field)
    legacy_raw = json.dumps(legacy).encode()
    legacy_digest = store.write_report(legacy_raw)
    old = read_reference(restored, owner.actor.owner_id, owner.actor.project_id, legacy_digest)
    assert old.schema_version == 1 and all(
        x.reported_init_model is None and x.request_sha256 is None for x in old.invocations
    )
    assert store.read_blob(legacy_digest) == legacy_raw
    # A protected receipt from different input cannot label this invocation.
    selected = observed_models[0]
    receipt = json.loads(owner.reports.read_blob(selected.receipt_sha256))
    receipt["context_sha256"] = "00" * 32
    mismatched = owner.reports.write_report(json.dumps(receipt).encode())
    with owner.connect() as c:
        c.execute(
            "UPDATE panestria.worker_invocation SET receipt_sha256=%s WHERE id=%s", (mismatched, selected.invocation_id)
        )
    with pytest.raises(KernelDenied, match="offline_reference_receipt_binding_mismatch"):
        owner.capture_reference(plan.goal_id)
    assert state["launches"] == 2
    diff = manifest.parts["diff"]
    raw = b"".join(store.read_blob(key) for key in diff.chunks)
    assert b"+value = 43" in raw and b"bounded Bash build" in raw
    target = store.root / diff.chunks[0]
    target.chmod(0o600)
    target.write_bytes(b"tampered archive output")
    with pytest.raises(KernelDenied, match="corrupt_build_evidence"):
        read_reference(restored, owner.actor.owner_id, owner.actor.project_id, digest)


def test_actual_archive_budget_failure_preserves_confirmed_merge_without_new_native_calls(native_plan, prepared_plan):
    f, owner, _, plan = prepared_plan
    _, runner, _, state = native_plan
    enable_capture(owner, f)
    assert runner.run(plan.plan_id, public_subscription_run=True)["status"] == "WAITING_APPROVAL"
    root = f.root / "offline-results"
    root.mkdir(mode=0o700)
    blobs = root / "blobs"
    blobs.mkdir(mode=0o700)
    with (blobs / "sparse-budget-fixture").open("wb") as stream:
        stream.truncate(8 * 1024 * 1024)
    result = approve(owner, plan.goal_id)
    assert result["task_state"] == "COMPLETED" and result["offline_reference"]["status"] == "UNAVAILABLE"
    assert state["launches"] == 2 and git(f.bare, "rev-parse", "HEAD") == result["candidate_commit"]
    assert len(list(blobs.iterdir())) == 1
    with pytest.raises(KernelDenied, match="history_budget_reached"):
        owner.capture_reference(plan.goal_id)
    assert len(list(blobs.iterdir())) == 1
