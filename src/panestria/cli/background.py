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


@background_app.command("probe-account")
def probe_account(config: Config, item_id: str) -> None:
    """Inspect pinned private Claude login metadata; retain only scoped identity hashes."""
    from panestria.execution.background_account import probe_account as probe

    _finish(lambda: probe(_service(config), item_id))


@background_app.command("link-account")
def link_account(
    config: Config, item_id: str, observation_sha256: str, link_sha256: str, accept_account_link: bool = False
) -> None:
    """Confirm the exact displayed pseudonymous profile/account link; no inference grant."""
    from panestria.execution.background_account import account_reports
    from panestria.kernel.background_account import BackgroundAccountService

    def run() -> dict[str, Any]:
        owner = _service(config)
        service = BackgroundAccountService(account_reports(owner))
        with owner.connect() as c:
            return service.confirm(
                UnitOfWork(c),
                owner.actor,
                item_id,
                observation_sha256,
                link_sha256,
                accept_account_link=accept_account_link,
            )

    _finish(run)


@background_app.command("account")
def show_account(config: Config, item_id: str) -> None:
    """Read a retained account link/freshness without contacting Claude or refreshing it."""
    from panestria.execution.background_account import account_reports
    from panestria.kernel.background_account import BackgroundAccountService

    def run() -> dict[str, Any]:
        owner = _service(config)
        service = BackgroundAccountService(account_reports(owner))
        with owner.connect() as c:
            return service.inspect(UnitOfWork(c), owner.actor, item_id)

    _finish(run)


@background_app.command("run")
def run_item(config: Config, item_id: str, allow_background_subscription_run: bool = False) -> None:
    """Run one reviewed bounded job, serially; yield new claims to foreground work."""
    from panestria.execution.background_run import BackgroundPlanRunner

    def run() -> dict[str, Any]:
        runner = BackgroundPlanRunner(_service(config), item_id)
        return runner.run_item(allow_background_subscription_run=allow_background_subscription_run)

    _finish(run)


@background_app.command("next")
def next_candidate(config: Config) -> None:
    """Preview the highest priority eligible unstarted item without probing or dispatch."""
    from panestria.execution.background_run import select_next

    _finish(lambda: select_next(_service(config)))


@background_app.command("run-next")
def run_next(config: Config, allow_background_subscription_run: bool = False) -> None:
    """Select and re-admit at most one reviewed job; no retry, fallback, resume or daemon."""
    from panestria.execution.background_run import run_next as execute_next

    _finish(lambda: execute_next(_service(config), allow_background_subscription_run=allow_background_subscription_run))


@background_app.command("reconcile-run")
def reconcile_run(config: Config, item_id: str, run_sha256: str) -> None:
    """Confirm an abandoned coordinator stopped only when no claim/invocation is uncertain."""
    from panestria.execution.background_run import reconcile_run as reconcile

    _finish(lambda: reconcile(_service(config), item_id, run_sha256))


@background_app.command("runs")
def list_runs(config: Config, item_id: str) -> None:
    """Inspect immutable coordinator history and separately held canonical claims."""
    from panestria.execution.background_account import account_reports
    from panestria.kernel.background_run import BackgroundRunService
    from panestria.kernel.build import BuildEvidenceService

    def run() -> dict[str, Any]:
        owner = _service(config)
        with owner.connect() as c:
            return BackgroundRunService(account_reports(owner), BuildEvidenceService(owner.reports)).listing(
                UnitOfWork(c), owner.actor, item_id
            )

    _finish(run)
