"""Explicit owner review and inspection of bounded background intent, not dispatch."""

import json
from datetime import timedelta
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

import typer

from panestria.cli.build import _finish, _service
from panestria.config_local import read_private
from panestria.contracts.background import BackgroundEnqueue
from panestria.kernel.background import BackgroundWorkService
from panestria.kernel.plan_store import PlanStore
from panestria.kernel.uow import UnitOfWork

background_app = typer.Typer(no_args_is_help=True)
Config = Annotated[Path, typer.Option("--config")]
Request = Annotated[Path, typer.Option("--request")]


@background_app.command("draft")
def draft(config: Config, plan_id: str, account_ref: str, output: Annotated[Path, typer.Option("--output")]) -> None:
    """Write a private review-only request from an accepted plan, with billing/quota unknown."""
    from panestria.cli.research import _write_private

    def run() -> dict[str, Any]:
        owner = _service(config)
        with owner.connect() as c:
            plan = PlanStore().get(UnitOfWork(c), owner.actor, plan_id)
            clock = c.execute("SELECT clock_timestamp()").fetchone()
            assert clock is not None
            request = BackgroundEnqueue.model_validate_json(
                json.dumps(
                    {
                        "schema_version": 1,
                        "item_id": str(uuid4()),
                        "plan_id": plan_id,
                        "expected_plan_sha256": plan.proposal.sha256(),
                        "policy": {
                            "policy_id": str(uuid4()),
                            "owner_id": owner.actor.owner_id,
                            "project_id": owner.actor.project_id,
                            "quota_windows": [
                                {"provider": "claude-subscription", "account_ref": account_ref, "window_ref": window}
                                for window in ("session", "weekly")
                            ],
                            "maximum_job_wall_seconds": min(
                                900, sum(n.attempts * n.wall_seconds_per_attempt for n in plan.proposal.nodes)
                            ),
                            "expires_at": (clock[0] + timedelta(hours=1)).isoformat(),
                        },
                    }
                )
            )
            binding = BackgroundWorkService().prepare(UnitOfWork(c), owner.actor, request)
        _write_private(output, request.model_dump_json(indent=2).encode())
        return {
            "status": "DRAFTED",
            "policy_sha256": binding.policy_sha256,
            "billing": "UNKNOWN",
            "execution_authority": "NONE",
        }

    _finish(run)


@background_app.command("prepare")
def prepare(config: Config, request: Request) -> None:
    """Preview exact plan/policy bindings and current waiting reasons; no write or model call."""

    def run() -> dict[str, Any]:
        owner = _service(config)
        submission = BackgroundEnqueue.model_validate_json(read_private(request, 16384))
        with owner.connect() as c:
            service, uow = BackgroundWorkService(), UnitOfWork(c)
            binding = service.prepare(uow, owner.actor, submission)
            return {
                "status": "REVIEW_ONLY",
                "binding": binding.model_dump(mode="json"),
                "binding_sha256": binding.sha256(),
                "policy_sha256": binding.policy_sha256,
                "eligibility": service.inspect(uow, owner.actor, binding),
                "execution_authority": "NONE",
            }

    _finish(run)


@background_app.command("enqueue")
def enqueue(config: Config, request: Request, policy_sha256: str, accept_background_policy: bool = False) -> None:
    """Record exact owner-reviewed background intent for an existing unstarted accepted plan."""

    def run() -> dict[str, Any]:
        owner = _service(config)
        submission = BackgroundEnqueue.model_validate_json(read_private(request, 16384))
        with owner.connect() as c:
            return BackgroundWorkService().enqueue(
                UnitOfWork(c), owner.actor, submission, policy_sha256, accept_background_policy=accept_background_policy
            )

    _finish(run)


@background_app.command("list")
def listing(config: Config) -> None:
    """Inspect the latest32 queued bindings against current canonical state and quota evidence."""

    def run() -> dict[str, Any]:
        owner = _service(config)
        with owner.connect() as c:
            return BackgroundWorkService().listing(UnitOfWork(c), owner.actor)

    _finish(run)


@background_app.command("show")
def show(config: Config, item_id: str) -> None:
    """Inspect one scoped queued item, including an older entry outside the list window."""

    def run() -> dict[str, Any]:
        owner = _service(config)
        with owner.connect() as c:
            return BackgroundWorkService().show(UnitOfWork(c), owner.actor, item_id)

    _finish(run)


@background_app.command("withdraw")
def withdraw(config: Config, item_id: str, binding_sha256: str) -> None:
    """Withdraw exact queued intent without cancelling the underlying goal or freeing claims."""

    def run() -> dict[str, Any]:
        owner = _service(config)
        with owner.connect() as c:
            return BackgroundWorkService().withdraw(UnitOfWork(c), owner.actor, item_id, binding_sha256)

    _finish(run)
