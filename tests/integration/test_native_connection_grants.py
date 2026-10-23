"""Actual canonical grants/Git/MCP/Docker; native/account/capacity are explicit fixtures."""

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from test_admitted_native_build import NativeTransportFixture
from test_background_queue import cli as background_cli
from test_background_run import setup as setup_background
from test_native_plan_execution import native_plan as native_plan  # noqa: F401
from test_native_plan_execution import owner_cli as owner_cli  # noqa: F401
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401
from test_owner_build_cli import contract as owner_contract
from typer.testing import CliRunner

from panestria.brokers.harness.claude_build import ClaudeScopedBashAdapter
from panestria.brokers.harness.claude_check import REQUESTED_MODEL
from panestria.brokers.harness.claude_proposal import PINNED_BINARY_SHA256
from panestria.cli.connection_terminal import review_lines
from panestria.cli.main import app
from panestria.contracts.build import canonical_sha256
from panestria.contracts.connections import (
    ConnectionBudget,
    ConnectionManifest,
    ConnectionReviewRequest,
    ConnectionReviewView,
    SubmitReview,
)
from panestria.contracts.native_account import NativeAccountObservation
from panestria.contracts.native_connection import (
    NativeConnectionReservation,
    NativeConnectionSelection,
    native_configuration,
)
from panestria.execution import background_account, native_connection
from panestria.execution.background_run import BackgroundPlanRunner
from panestria.execution.build_plan import BuildIntegrator
from panestria.execution.native_build import runtime_versions
from panestria.kernel.connections import ConnectionReviewService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.native_connection import NativeConnectionBroker
from panestria.kernel.uow import UnitOfWork

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def source(record_property):
    record_property(
        "candidate_commit", subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    )
    record_property(
        "worktree_state",
        "dirty" if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip() else "clean",
    )
    record_property("scope", "ACTUAL_PG_GIT_MCP_DOCKER__SYNTHETIC_NATIVE_ACCOUNT_AUTH_CAPACITY_NOT_LIVE_QUALIFICATION")


def setup(native_plan, monkeypatch, *, max_calls=2, max_bytes=32768, observation_sha256=None):
    owner, runner, plan, state = native_plan
    state["identity"] = "12" * 32
    reports = background_account.account_reports(owner)
    account = str(uuid4())

    def collect(_owner, account_ref):
        observed = NativeAccountObservation(
            owner_id=owner.actor.owner_id,
            project_id=owner.actor.project_id,
            account_ref=account_ref,
            observed_at=datetime.now(UTC),
            identity_sha256=state["identity"],
            identity_basis="ACCOUNT_ID",
            profile_sha256=canonical_sha256(
                {"fixture_private_profile": str(owner.settings.native_config), "account": account_ref}
            ),
            binary_sha256=PINNED_BINARY_SHA256,
            compatibility_sha256="34" * 32,
            subscription_type="max",
        )
        return reports.write_report(
            json.dumps(observed.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
        )

    if observation_sha256 is None:
        monkeypatch.setattr(native_connection, "collect_account", collect)
        monkeypatch.setattr(background_account, "collect_account", collect)
        digest = collect(owner, account)
    else:
        # Background's supported probe and native selection inspect the same
        # synthetic CLI metadata through the actual private observation helper.
        digest = observation_sha256
    anchor = NativeAccountObservation.model_validate_json(reports.read_blob(digest))
    model = owner.settings.native_model
    with owner.connect() as c:
        scope = ConnectionReviewService().scope(UnitOfWork(c), owner.actor)
    manifest = ConnectionManifest(
        schema_version=3 if model is not None else 2,
        owner_id=owner.actor.owner_id,
        project_id=owner.actor.project_id,
        connector_ref="claude-public-bash",
        connector_version="model-context-v2" if model is not None else "account-context-v1",
        requested_model=model,
        provider_route="claude-subscription",
        budget_scope="SELECTED_PUBLIC_CONTEXT_AND_NATIVE_LAUNCHES",
        account_ref=anchor.account_ref,
        root_refs=(anchor.profile_sha256,),
        configuration_sha256=native_configuration(anchor, runtime_versions(model), model or REQUESTED_MODEL),
        actions=("read", "write", "send"),
        data_classes=("PUBLIC",),
        budget=ConnectionBudget(max_calls=max_calls, max_bytes=max_bytes, max_wall_seconds=600),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        conformance_sha256=owner.settings.certificate_sha256,
    )
    service = ConnectionReviewService()
    with owner.connect() as c:
        review = service.propose(
            UnitOfWork(c),
            owner.actor,
            plan.nodes[0].task_id,
            ConnectionReviewRequest(
                proposal_id=str(uuid4()),
                policy_ref=scope.policy_ref,
                expected_version=0,
                operation="REPLACE",
                manifest=manifest,
            ),
        )
    with owner.connect() as c:
        decision = service.decide(UnitOfWork(c), owner.actor, review.proposal_id, review.effect_digest, "approve")
    selection = NativeConnectionSelection(
        grant_id=review.grant_id, version=decision.granted_version, account_observation_sha256=digest
    )
    owner.settings = owner.settings.model_copy(update={"native_connection": selection})

    def revoke():
        with owner.connect() as c:
            current = service.scope(UnitOfWork(c), owner.actor)
            pending = service.propose(
                UnitOfWork(c),
                owner.actor,
                plan.nodes[0].task_id,
                ConnectionReviewRequest(
                    proposal_id=str(uuid4()),
                    policy_ref=current.policy_ref,
                    grant_id=selection.grant_id,
                    expected_version=selection.version,
                    operation="REVOKE",
                ),
            )
        with owner.connect() as c:
            service.decide(UnitOfWork(c), owner.actor, pending.proposal_id, pending.effect_digest, "approve")

    return owner, runner, plan, state, anchor, revoke, manifest


def reservations(owner):
    with owner.connect() as c:
        return c.execute(
            "SELECT payload FROM panestria.task_event WHERE kind='native_connection.reserved' ORDER BY seq"
        ).fetchall()


def test_two_actual_scoped_workers_consume_exact_context_capacity_and_reach_final_review(native_plan, monkeypatch):
    owner, runner, plan, state, anchor, _, _ = setup(native_plan, monkeypatch)
    result = runner.run(plan.plan_id, public_subscription_run=True)
    assert result["status"] == "WAITING_APPROVAL", result
    assert state["launches"] == 2 and state["peak"] == 2
    rows = reservations(owner)
    assert len(rows) == 2
    for row in rows:
        body = NativeConnectionReservation.model_validate_json(json.dumps(row[0]["reservation"]))
        assert body.sha256() == row[0]["reservation_sha256"]
        context = next(c for c in state["contexts"] if c["assignment"]["task_id"] == str(body.scope.task_id))
        raw = json.dumps(context, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        assert body.context_bytes == len(raw)
        assert body.context_sha256 == __import__("hashlib").sha256(raw).hexdigest()
        assert "value = " not in json.dumps(row) and str(owner.settings.native_config) not in json.dumps(row)
        with owner.connect() as c:
            c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            NativeConnectionBroker().require_reserved(UnitOfWork(c), owner.actor, body, anchor)
    with owner.connect() as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.build_handoff WHERE plan_id=%s", (plan.plan_id,)
        ).fetchone() == (2,)
        assert c.execute(
            "SELECT count(*) FROM panestria.approval_request WHERE goal_id=%s", (plan.goal_id,)
        ).fetchone() == (1,)
    assert owner.status(plan.goal_id)["task_state"] == "WAITING_APPROVAL"


def test_revoke_before_run_denies_before_claim_or_native_metadata_disclosure(native_plan, monkeypatch):
    owner, runner, plan, state, _, revoke, _ = setup(native_plan, monkeypatch)
    revoke()
    with pytest.raises(KernelDenied, match="native_connection_not_current"):
        runner.run(plan.plan_id, public_subscription_run=True)
    assert state["launches"] == 0 and reservations(owner) == []
    with owner.connect() as c:
        assert c.execute("SELECT count(*) FROM panestria.task_attempt").fetchone() == (0,)


def test_account_changed_after_claim_cannot_disclose_or_publish(native_plan, monkeypatch):
    owner, runner, plan, state, _, _, _ = setup(native_plan, monkeypatch)
    original = ClaudeScopedBashAdapter.build_public

    def changed(adapter, session, **kwargs):
        before = kwargs["before_launch"]

        def callback():
            state["identity"] = "56" * 32
            before()

        return original(adapter, session, **{**kwargs, "before_launch": callback})

    monkeypatch.setattr(ClaudeScopedBashAdapter, "build_public", changed)
    result = runner.run(plan.plan_id, public_subscription_run=True)
    assert result["status"] == "STOPPED" and state["launches"] == 0, result
    with owner.connect() as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.task_event WHERE kind='native_build.context_disclosure'"
        ).fetchone() == (0,)
        assert c.execute("SELECT count(*) FROM panestria.build_evidence").fetchone() == (0,)


def test_inflight_revocation_interrupts_supervised_workers_without_acceptance(native_plan, monkeypatch):
    owner, runner, plan, state, _, revoke, _ = setup(native_plan, monkeypatch)
    state["block"] = True
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(lambda: runner.run(plan.plan_id, public_subscription_run=True))
        assert state["started"].wait(12)
        revoke()
        result = future.result(timeout=15)
    assert result["status"] == "STOPPED" and state["launches"] == 2, result
    assert all(r["status"] == "CANCELLED" for r in result["worker_observations"])
    assert len(reservations(owner)) == 2  # no refund/replay after uncertainty
    with owner.connect() as c:
        assert c.execute("SELECT count(*) FROM panestria.build_evidence").fetchone() == (0,)
        assert c.execute("SELECT count(*) FROM panestria.build_active_worker_claim").fetchone() == (2,)


@pytest.mark.parametrize("limits", [{"max_calls": 1}, {"max_bytes": 1}])
def test_shared_capacity_stops_concurrent_excess_without_fallback(native_plan, monkeypatch, limits):
    owner, runner, plan, state, _, _, _ = setup(native_plan, monkeypatch, **limits)
    state["expected_workers"] = 1  # fixture transport has no two-worker barrier
    result = runner.run(plan.plan_id, public_subscription_run=True)
    assert result["status"] == "STOPPED", result
    expected = 0 if "max_bytes" in limits else 1
    assert state["launches"] == len(reservations(owner)) == expected
    with owner.connect() as c:
        assert c.execute("SELECT count(*) FROM panestria.approval_request").fetchone() == (0,)


def test_revoke_during_final_checks_keeps_returned_worker_evidence_but_no_final_review(native_plan, monkeypatch):
    owner, runner, plan, state, _, revoke, _ = setup(native_plan, monkeypatch)
    original = BuildIntegrator._authorize
    changed = []

    def guarded(controller):
        if not changed:
            changed.append(True)
            revoke()
        return original(controller)

    monkeypatch.setattr(BuildIntegrator, "_authorize", guarded)
    with pytest.raises(KernelDenied, match="native_connection_not_current"):
        runner.run(plan.plan_id, public_subscription_run=True)
    assert changed and state["launches"] == 2
    with owner.connect() as c:
        assert c.execute("SELECT count(*) FROM panestria.build_handoff").fetchone() == (2,)
        assert c.execute("SELECT count(*) FROM panestria.approval_request").fetchone() == (0,)


@pytest.mark.parametrize("withdraw", [None, "connection", "queue"])
def test_native_and_background_authorities_both_fence_final_publication(
    prepared_plan, native_plan, monkeypatch, withdraw
):
    f, owner, plan, state, request, view = setup_background(prepared_plan, native_plan, monkeypatch)
    _, _, _, _, _, revoke, _ = setup(native_plan, monkeypatch, observation_sha256=view["observation_sha256"])
    original = BuildIntegrator._authorize
    reached = []

    def guarded(controller):
        if not reached:
            reached.append(withdraw)
            if withdraw == "connection":
                revoke()
            elif withdraw == "queue":
                current = background_cli(f, "show", request.item_id)
                background_cli(f, "withdraw", request.item_id, current["binding_sha256"])
        return original(controller)

    monkeypatch.setattr(BuildIntegrator, "_authorize", guarded)
    result = BackgroundPlanRunner(owner, request.item_id).run_item(allow_background_subscription_run=True)
    assert reached == [withdraw] and state["launches"] == 2
    assert len(reservations(owner)) == 2
    if withdraw is None:
        assert result["status"] == "WAITING_APPROVAL", result
    else:
        assert result["status"] == "WAIT", result
        assert result["reason"] == (
            "native_connection_not_current" if withdraw == "connection" else "background_item_withdrawn"
        )
    with owner.connect() as c:
        assert c.execute("SELECT count(*) FROM panestria.build_handoff").fetchone() == (2,)
        assert c.execute("SELECT count(*) FROM panestria.approval_request").fetchone() == (
            (1,) if withdraw is None else (0,)
        )


def test_single_owner_build_also_reserves_the_selected_connection(prepared_plan, native_plan, monkeypatch):
    owner, _, _, _, _, _, _ = setup(native_plan, monkeypatch, max_calls=1)
    f = prepared_plan[0]

    def native(adapter, *args, **kwargs):
        return NativeTransportFixture.build_public(f.transport, *args, **kwargs)

    monkeypatch.setattr(ClaudeScopedBashAdapter, "build_public", native)
    with owner.connect() as c:
        policy_ref = ConnectionReviewService().scope(UnitOfWork(c), owner.actor).policy_ref
    document = owner_contract(f, policy_ref)
    result = owner.submit(document, ("calculator.py",), f.base, document["goal_id"], public_subscription_run=True)
    assert result["task_state"] == "WAITING_APPROVAL", result
    assert f.transport.launches == 1 and len(reservations(owner)) == 1


def test_native_cli_template_and_terminal_expose_exact_route_and_units_without_enabling(
    native_plan, monkeypatch, tmp_path
):
    owner, _, plan, _, anchor, _, _ = setup(native_plan, monkeypatch)
    with owner.connect() as c:
        scope = ConnectionReviewService().scope(UnitOfWork(c), owner.actor)
    monkeypatch.setattr("panestria.cli.build._service", lambda _: owner)
    monkeypatch.setattr("panestria.cli.connection_client.ConnectionClient.scope", lambda _: scope)
    directory = tmp_path / "connections"
    configured = CliRunner().invoke(
        app,
        [
            "connections",
            "init",
            "--directory",
            str(directory),
            "--owner-id",
            owner.actor.owner_id,
            "--project-id",
            owner.actor.project_id,
        ],
    )
    assert configured.exit_code == 0, configured.output
    output = tmp_path / "native-proposal.json"
    result = CliRunner().invoke(
        app,
        [
            "connections",
            "native-template",
            "--config",
            str(directory / "activity.json"),
            "--build-config",
            str(tmp_path / "build.json"),
            "--task-id",
            plan.nodes[0].task_id,
            "--proposal-id",
            str(uuid4()),
            "--account-ref",
            anchor.account_ref,
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    response = json.loads(result.output)
    assert response["runtime_available"] is False and response["billing_verified"] is False
    request = SubmitReview.model_validate_json(output.read_bytes())
    assert request.change.manifest.schema_version == 2 and output.stat().st_mode & 0o777 == 0o600
    with owner.connect() as c:
        pending = ConnectionReviewService().propose(UnitOfWork(c), owner.actor, plan.nodes[0].task_id, request.change)
    view = ConnectionReviewView(
        schema_version=1,
        proposal_id=pending.proposal_id,
        grant_id=pending.grant_id,
        expected_version=0,
        effect_digest=pending.effect_digest,
        operation="REPLACE",
        policy_ref=pending.policy_ref,
        review_expires_at=pending.expires_at,
        manifest=pending.manifest,
        state="PENDING",
        replayed=False,
        authority="DECLARATION_ONLY",
        conformance_status="UNVERIFIED",
        runtime_available=False,
    )
    displayed = "".join(review_lines(view, 100))  # Fixed-cell wrapping can split a word across rows.
    assert "claude-subscription" in displayed and "selected PUBLIC context only" in displayed
    assert "Wire traffic and billing are not measured" in displayed
    assert "fences future selected native work" in displayed
