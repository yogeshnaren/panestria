"""Actual PG/Git/MCP/Docker with synthetic native/model/account/certificates."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_native_connection_grants import reservations, setup
from test_native_plan_execution import native_plan as native_plan  # noqa: F401
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401
from test_owner_build_cli import owner_cli as owner_cli  # noqa: F401

from panestria.cli.connection_terminal import review_lines
from panestria.contracts.connections import ConnectionReviewView
from panestria.contracts.native_connection import NativeConnectionReservation
from panestria.execution.native_connection import preflight_connection
from panestria.kernel.connections import ConnectionReviewService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.uow import UnitOfWork


@pytest.mark.parametrize("owner_cli", [{"native_model": "claude-sonnet-5"}], indirect=True)
def test_selected_two_worker_model_reaches_exact_review_with_retained_grant_and_invocation(native_plan, monkeypatch):
    owner, runner, plan, state, anchor, _, manifest = setup(native_plan, monkeypatch)
    selected = "claude-sonnet-5"
    assert manifest.schema_version == 3 and manifest.requested_model == selected
    with owner.connect() as c:
        grant = ConnectionReviewService().current(UnitOfWork(c), owner.actor, owner.settings.native_connection.grant_id)
    view = ConnectionReviewView(
        schema_version=1,
        proposal_id=plan.plan_id,
        grant_id=grant.grant_id,
        expected_version=0,
        effect_digest="ab" * 32,
        operation="REPLACE",
        policy_ref=grant.policy_ref,
        review_expires_at=manifest.expires_at,
        manifest=manifest,
        state="APPROVED",
        replayed=False,
        authority="DECLARATION_ONLY",
        conformance_status="UNVERIFIED",
        runtime_available=False,
    )
    assert selected in " ".join(review_lines(view, 120))
    result = runner.run(plan.plan_id, public_subscription_run=True)
    assert result["status"] == "WAITING_APPROVAL", result
    assert state["launches"] == 2 and state["peak"] == 2
    recorded = [
        NativeConnectionReservation.model_validate_json(json.dumps(r[0]["reservation"])) for r in reservations(owner)
    ]
    assert len(recorded) == 2 and all(r.requested_model == selected for r in recorded)
    with owner.connect() as c:
        rows = c.execute(
            "SELECT binding,receipt_sha256 FROM panestria.worker_invocation WHERE binding->>'kind'='native-proposal'"
        ).fetchall()
    assert len(rows) == 2
    for row in rows:
        receipt = json.loads(owner.reports.read_blob(str(row[1]).strip()))
        assert receipt["runtime_versions"]["requested_model"] == selected
        assert receipt["observation"]["requested_model"] == selected
        assert receipt["observation"]["process"]["result"]["reported_init_model"] == selected
    # Model-scoped queue admission is covered separately in test_background_model_scope.


@pytest.mark.parametrize("owner_cli", [{"native_model": "claude-sonnet-5"}], indirect=True)
def test_visible_model_mismatch_cannot_hide_behind_correct_configuration_hash(native_plan, monkeypatch):
    owner, runner, plan, state, _, _, manifest = setup(native_plan, monkeypatch)
    service = ConnectionReviewService()
    original = service.current

    def mismatched(self, *args, **kwargs):
        grant = original(*args, **kwargs)
        return replace(grant, manifest=manifest.model_copy(update={"requested_model": "claude-opus-5"}))

    monkeypatch.setattr(service.__class__, "current", mismatched)
    with pytest.raises(KernelDenied, match="native_connection_not_current"):
        preflight_connection(owner)
    assert state["launches"] == 0 and not reservations(owner)


@pytest.mark.parametrize("owner_cli", [{"native_model": "claude-sonnet-5"}], indirect=True)
def test_selected_model_requires_explicit_grant_and_matching_certificate(native_plan):
    owner, runner, plan, state = native_plan
    with pytest.raises(KernelDenied, match="selected_model_requires_reviewed_native_connection"):
        runner._preflight(plan.plan_id)
    assert state["launches"] == 0
    assert owner.certificates.runtime_versions["requested_model"] == "claude-sonnet-5"
    # A legacy certificate or changed inventory never becomes selected-model conformance.
    owner.settings = owner.settings.model_copy(update={"native_model": None})
    with pytest.raises(KernelDenied, match="public_native_plan_not_eligible"):
        runner._preflight(plan.plan_id)
    assert state["launches"] == 0


@pytest.mark.live
@pytest.mark.parametrize("model", ["claude-sonnet-5", "claude-opus-5"])
def test_pinned_selected_model_zero_turn_empty_auth_startup(model, record_property, monkeypatch):
    """Native metadata only: no owner auth, provider inference, edits or qualification."""
    import subprocess
    from dataclasses import asdict

    from panestria.brokers.harness import claude_check
    from panestria.brokers.harness.bash_protocol import ScopedBashSession
    from panestria.brokers.harness.claude_build import ClaudeScopedBashAdapter
    from panestria.brokers.harness.claude_proposal import PINNED_BINARY_SHA256, ClaudeProposalAdapter
    from panestria.brokers.harness.cli_profile import BinaryPin
    from panestria.contracts.native_command import RegisteredCheckReceipt

    root = Path(__file__).resolve().parents[2]
    original = claude_check.run_metadata

    def observed_metadata(*args):
        output = original(*args)
        record_property("startup_stdout", output.stdout.decode("utf-8"))
        return output

    monkeypatch.setattr(claude_check, "run_metadata", observed_metadata)
    calls = []
    session = ScopedBashSession(
        "scoped-bash:" + "ab" * 32, lambda *a: calls.append(a) or RegisteredCheckReceipt(outcome="DENIED")
    )
    native = ClaudeProposalAdapter(
        BinaryPin(Path.home() / ".local/share/claude/versions/2.1.273", PINNED_BINARY_SHA256),
        Path("/tmp/panestria-no-owner-login-used"),
        root / "docs/specification/attachments/agentos-skills-v0.1.0.zip",
    )
    observed = ClaudeScopedBashAdapter(native, native_model=model).build_public(
        session, public_context="PUBLIC synthetic startup only; no tool or inference.", startup_only=True
    )
    record_property(
        "candidate_commit", subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    )
    record_property("observation", json.dumps(asdict(observed), sort_keys=True))
    record_property("scope", "ACTUAL_PINNED_ZERO_TURN_EMPTY_AUTH_METADATA_ONLY_NOT_INFERENCE_OR_QUALIFICATION")
    assert observed.process is None and observed.startup_observed and observed.hostile_configuration_ignored
    assert observed.requested_model == model and not calls
