"""Actual PG/Git/MCP/Docker with synthetic native/model/account/certificates."""

import json
from dataclasses import replace

import pytest
from test_native_connection_grants import reservations, setup
from test_native_plan_execution import native_plan as native_plan  # noqa: F401
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401
from test_owner_build_cli import owner_cli as owner_cli  # noqa: F401

from panestria.cli.connection_terminal import review_lines
from panestria.contracts.connections import ConnectionReviewView
from panestria.contracts.native_connection import NativeConnectionReservation
from panestria.execution.background_run import BackgroundPlanRunner
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
            "SELECT binding FROM panestria.worker_invocation WHERE binding->>'kind'='native-proposal'"
        ).fetchall()
    assert len(rows) == 2
    for row in rows:
        assert row[0]["configuration_sha256"]
    # Foreground selection cannot reinterpret a legacy reviewed background policy.
    with pytest.raises(KernelDenied, match="background_selected_model_not_supported"):
        BackgroundPlanRunner(owner, plan.plan_id)._preflight(plan.plan_id)


@pytest.mark.parametrize("owner_cli", [{"native_model": "claude-sonnet-5"}], indirect=True)
def test_visible_model_mismatch_cannot_hide_behind_correct_configuration_hash(native_plan, monkeypatch):
    owner, runner, plan, state, _, _, manifest = setup(native_plan, monkeypatch)
    service = ConnectionReviewService()
    original = service.current

    def mismatched(self, *args, **kwargs):
        grant = original(self, *args, **kwargs)
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
