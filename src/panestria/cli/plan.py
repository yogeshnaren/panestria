"""Private-file Build DAG preflight and explicitly reviewed canonical retention."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import typer

from panestria.config_local import read_private
from panestria.contracts.goal import load_contract
from panestria.contracts.plan import PlanProposal, ProjectInventory
from panestria.kernel.goals import Actor
from panestria.kernel.plans import PlanValidator

if TYPE_CHECKING:
    from psycopg import Connection

    from panestria.kernel.build import BuildEvidenceService

plan_app = typer.Typer(no_args_is_help=True)


@plan_app.command("validate")
def validate_plan(
    owner_id: str,
    project_id: str,
    proposal: Annotated[Path, typer.Option("--proposal")],
    contract: Annotated[Path, typer.Option("--contract")],
    inventory: Annotated[Path, typer.Option("--inventory")],
) -> None:
    """Check bounded task dependencies/scope/capabilities/budget; never admits a worker."""
    try:
        result = PlanValidator().validate(
            Actor(owner_id, project_id),
            PlanProposal.model_validate_json(read_private(proposal, 128 * 1024)),
            load_contract(json.loads(read_private(contract, 256 * 1024))),
            ProjectInventory.model_validate_json(read_private(inventory, 16384)),
        )
        typer.echo(result.model_dump_json())
    except Exception:
        typer.echo('{"status":"UNAVAILABLE","reason":"plan_proposal_rejected","authority":"NONE"}', err=True)
        raise typer.Exit(1) from None


def _connection() -> Connection[Any]:
    import os

    import psycopg

    from panestria.config import Settings

    dsn = Settings(database_url=os.environ.get("PANESTRIA_DATABASE_URL", "")).validate_profile().database_url
    return psycopg.connect(
        dsn.get_secret_value(), connect_timeout=2, options="-c statement_timeout=5000 -c lock_timeout=2000"
    )


def _unavailable() -> None:
    typer.echo('{"status":"UNAVAILABLE","reason":"canonical_plan_not_confirmed_inspect_state"}', err=True)
    raise typer.Exit(1) from None


@plan_app.command("prepare")
def prepare_plan(
    owner_id: str,
    project_id: str,
    proposal: Annotated[Path, typer.Option("--proposal")],
    inventory: Annotated[Path, typer.Option("--inventory")],
) -> None:
    """Retain a proposal against the canonical goal; no task rows or worker permission."""
    from panestria.kernel.plan_store import PlanStore
    from panestria.kernel.uow import UnitOfWork

    try:
        with _connection() as c:
            result = PlanStore().prepare(
                UnitOfWork(c),
                Actor(owner_id, project_id),
                PlanProposal.model_validate_json(read_private(proposal, 128 * 1024)),
                ProjectInventory.model_validate_json(read_private(inventory, 16384)),
            )
        typer.echo(
            json.dumps(
                {
                    "plan_id": result.proposal.plan_id,
                    "effect_digest": result.effect_digest,
                    "state": result.state,
                    "execution_authority": "NONE",
                }
            )
        )
    except Exception:
        _unavailable()


@plan_app.command("accept")
def accept_plan_command(
    owner_id: str,
    project_id: str,
    plan_id: str,
    effect_digest: str,
    accept_plan: Annotated[bool, typer.Option("--accept-plan")] = False,
) -> None:
    """Confirm the exact owner plan review; create canonical CREATED task references only."""
    from panestria.kernel.plan_store import PlanStore
    from panestria.kernel.uow import UnitOfWork

    try:
        with _connection() as c:
            result = PlanStore().accept(
                UnitOfWork(c), Actor(owner_id, project_id), plan_id, effect_digest, accept_plan=accept_plan
            )
        typer.echo(
            json.dumps(
                {
                    "plan_id": plan_id,
                    "state": result.state,
                    "task_count": len(result.proposal.nodes),
                    "execution_authority": "NONE",
                }
            )
        )
    except Exception:
        _unavailable()


@plan_app.command("inspect")
def inspect_plan(
    owner_id: str, project_id: str, plan_id: str, output: Annotated[Path, typer.Option("--output")]
) -> None:
    """Export the canonical frozen plan/consent privately; does not admit or execute work."""
    from panestria.cli.research import _write_private
    from panestria.kernel.plan_store import PlanStore
    from panestria.kernel.uow import UnitOfWork

    try:
        with _connection() as c:
            result = PlanStore().get(UnitOfWork(c), Actor(owner_id, project_id), plan_id)
        _write_private(output, result.model_dump_json().encode())
        typer.echo(json.dumps({"plan_id": plan_id, "state": result.state, "effect_digest": result.effect_digest}))
    except Exception:
        _unavailable()


def _evidence_store(path: Path) -> BuildEvidenceService:
    import os

    from panestria.kernel.build import BuildEvidenceService, BuildEvidenceStore

    if not path.is_absolute() or path.resolve(strict=True) != path or not path.is_dir():
        raise ValueError("existing_private_evidence_store_required")
    if path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise ValueError("existing_private_evidence_store_required")
    return BuildEvidenceService(BuildEvidenceStore(path))


@plan_app.command("handoff")
def record_handoff(
    owner_id: str,
    project_id: str,
    submission: Annotated[Path, typer.Option("--submission")],
    evidence_store: Annotated[Path, typer.Option("--evidence-store")],
) -> None:
    """Bind an untrusted handoff note to actual current canonical verifier evidence."""
    from panestria.contracts.plan import HandoffSubmission
    from panestria.kernel.plan_store import PlanStore
    from panestria.kernel.uow import UnitOfWork

    try:
        evidence = _evidence_store(evidence_store)
        with _connection() as c:
            result = PlanStore().handoff(
                UnitOfWork(c),
                Actor(owner_id, project_id),
                HandoffSubmission.model_validate_json(read_private(submission, 8192)),
                evidence,
            )
        typer.echo(
            json.dumps(
                {
                    "handoff_id": result.submission.handoff_id,
                    "sha256": result.sha256(),
                    "task_completion_authority": "NONE",
                }
            )
        )
    except Exception:
        _unavailable()


@plan_app.command("inspect-handoff")
def inspect_handoff(
    owner_id: str,
    project_id: str,
    handoff_id: str,
    evidence_store: Annotated[Path, typer.Option("--evidence-store")],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    """Revalidate source-bound handoff and export privately for a fresh session."""
    from panestria.cli.research import _write_private
    from panestria.kernel.plan_store import PlanStore
    from panestria.kernel.uow import UnitOfWork

    try:
        evidence = _evidence_store(evidence_store)
        with _connection() as c:
            result = PlanStore().read_handoff(UnitOfWork(c), Actor(owner_id, project_id), handoff_id, evidence)
        _write_private(output, result.model_dump_json().encode())
        typer.echo(
            json.dumps({"handoff_id": handoff_id, "sha256": result.sha256(), "task_completion_authority": "NONE"})
        )
    except Exception:
        _unavailable()


@plan_app.command("queue")
def inspect_queue(
    owner_id: str,
    project_id: str,
    plan_id: str,
    evidence_store: Annotated[Path, typer.Option("--evidence-store")],
) -> None:
    """Inspect canonical readiness/wait reasons; does not dispatch or reserve work."""
    from dataclasses import asdict

    from panestria.kernel.scheduler import Scheduler
    from panestria.kernel.uow import UnitOfWork

    try:
        evidence = _evidence_store(evidence_store)
        with _connection() as c:
            result = Scheduler().inspect(UnitOfWork(c), Actor(owner_id, project_id), plan_id, evidence)
        typer.echo(json.dumps({"nodes": [asdict(node) for node in result], "dispatch_authority": "NONE"}))
    except Exception:
        _unavailable()


@plan_app.command("claim")
def claim_node(
    owner_id: str,
    project_id: str,
    plan_id: str,
    evidence_store: Annotated[Path, typer.Option("--evidence-store")],
    skills_archive: Annotated[Path, typer.Option("--skills-archive")],
) -> None:
    """Probe local CPU capacity and reserve one ready node. No process/model is launched."""
    from dataclasses import asdict

    from panestria.kernel.scheduler import Scheduled, Scheduler
    from panestria.kernel.uow import UnitOfWork
    from panestria.resources.hardware import HardwareProbe

    try:
        evidence = _evidence_store(evidence_store)
        capacity = HardwareProbe(skills_archive).collect_cpu()
        with _connection() as c:
            result = Scheduler().claim_ready(UnitOfWork(c), Actor(owner_id, project_id), plan_id, capacity, evidence)
        if isinstance(result, Scheduled):
            typer.echo(json.dumps({"status": "RESERVED", **asdict(result)}, default=str))
        else:
            typer.echo(json.dumps({"status": "WAIT", "nodes": [asdict(node) for node in result]}))
    except Exception:
        _unavailable()


@plan_app.command("complete-node")
def complete_plan_node(
    owner_id: str,
    project_id: str,
    plan_id: str,
    handoff_id: str,
    evidence_store: Annotated[Path, typer.Option("--evidence-store")],
) -> None:
    """Complete a current verified intermediate node; never completes/merges the goal."""
    from panestria.kernel.scheduler import Scheduler
    from panestria.kernel.uow import UnitOfWork

    try:
        evidence = _evidence_store(evidence_store)
        with _connection() as c:
            Scheduler().complete_node(UnitOfWork(c), Actor(owner_id, project_id), plan_id, handoff_id, evidence)
        typer.echo('{"status":"NODE_COMPLETED","goal_completion_authority":"NONE"}')
    except Exception:
        _unavailable()


@plan_app.command("claims")
def inspect_claims(owner_id: str, project_id: str, plan_id: str) -> None:
    """Inspect historical reservations, including after lease expiry or policy changes."""
    from panestria.kernel.scheduler import Scheduler
    from panestria.kernel.uow import UnitOfWork

    try:
        with _connection() as c:
            result = Scheduler().claims(UnitOfWork(c), Actor(owner_id, project_id), plan_id)
        typer.echo(json.dumps({"claims": result, "dispatch_authority": "NONE"}, default=str))
    except Exception:
        _unavailable()


@plan_app.command("integrate")
def integrate_plan(
    config: Annotated[Path, typer.Option("--config")],
    plan_id: str,
    attempt_id: str,
    epoch: int,
) -> None:
    """Combine verified completed nodes and run full final-tree checks; stop at owner review."""
    from uuid import uuid4

    from panestria.cli.build import _finish, _service
    from panestria.config_build import _directory
    from panestria.execution.build_plan import BuildIntegrator
    from panestria.kernel.build import BuildEvidenceService

    def run() -> dict[str, Any]:
        owner = _service(config)
        parent = owner.settings.root / "plan-integration"
        parent.mkdir(mode=0o700, exist_ok=True)
        _directory(parent)
        result = BuildIntegrator(owner.connect, owner.actor, BuildEvidenceService(owner.reports), owner.certificates)
        outcome = result.verify_for_review(
            plan_id,
            attempt_id,
            epoch,
            owner.settings.protected,
            owner.settings.repository,
            parent / str(uuid4()),
            owner.registry,
        )
        payload: dict[str, Any] = {"status": outcome.status, "report_sha256": outcome.report_sha256}
        if outcome.review is not None:
            review = outcome.review
            payload["review"] = {
                "candidate_commit": review.candidate_commit,
                "evidence_sha256": review.evidence_sha256,
                "passed": review.passed,
                "approval": vars(review.approval) if review.approval else None,
            }
        return payload

    _finish(run)


@plan_app.command("cancel")
def cancel_plan(owner_id: str, project_id: str, plan_id: str, proposal_sha256: str) -> None:
    """Withdraw the exact accepted plan across all tasks, even after policy revocation."""
    from dataclasses import asdict

    from panestria.kernel.plan_lifecycle import PlanLifecycle
    from panestria.kernel.uow import UnitOfWork

    try:
        with _connection() as c:
            receipt = PlanLifecycle().cancel(UnitOfWork(c), Actor(owner_id, project_id), plan_id, proposal_sha256)
        typer.echo(json.dumps(asdict(receipt)))
    except Exception:
        _unavailable()


@plan_app.command("release-final")
def release_final_capacity(
    owner_id: str,
    project_id: str,
    plan_id: str,
    task_id: str,
    evidence_sha256: str,
    effect_id: str,
    evidence_store: Annotated[Path, typer.Option("--evidence-store")],
) -> None:
    """Reconcile only a completed, confirmed final merge's capacity hold; never dispatch."""
    from panestria.kernel.plan_lifecycle import PlanLifecycle
    from panestria.kernel.uow import UnitOfWork

    try:
        evidence = _evidence_store(evidence_store)
        with _connection() as c:
            proof = PlanLifecycle().release_final(
                UnitOfWork(c), Actor(owner_id, project_id), plan_id, task_id, evidence_sha256, effect_id, evidence
            )
        typer.echo(json.dumps({"status": "RELEASED", "proof_sha256": proof, "dispatch_authority": "NONE"}))
    except Exception:
        _unavailable()


@plan_app.command("stage")
def stage_public_plan(
    owner_id: str,
    project_id: str,
    contract: Annotated[Path, typer.Option("--contract")],
    proposal: Annotated[Path, typer.Option("--proposal")],
    inventory: Annotated[Path, typer.Option("--inventory")],
    idempotency_key: Annotated[str, typer.Option("--idempotency-key")],
) -> None:
    """Stage a PUBLIC zero-cash goal/checks and plan; requires separate exact owner acceptance."""
    from dataclasses import asdict

    from panestria.kernel.plan_submission import PlanSubmissionService
    from panestria.kernel.uow import UnitOfWork

    try:
        with _connection() as c:
            receipt = PlanSubmissionService().stage(
                UnitOfWork(c),
                Actor(owner_id, project_id),
                json.loads(read_private(contract, 256 * 1024)),
                PlanProposal.model_validate_json(read_private(proposal, 128 * 1024)),
                ProjectInventory.model_validate_json(read_private(inventory, 16384)),
                idempotency_key,
            )
        typer.echo(json.dumps(asdict(receipt)))
    except Exception:
        _unavailable()
