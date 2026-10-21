"""Explicit local owner submission and exact review of PUBLIC native Build work."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

import typer

from panestria.config import Settings
from panestria.config_build import load_build_settings
from panestria.config_local import read_private
from panestria.execution.owner_build import OwnerBuild
from panestria.kernel.errors import KernelDenied

build_app = typer.Typer(no_args_is_help=True)
Config = Annotated[Path, typer.Option("--config")]


@build_app.command("tui")
def terminal_review(config: Config, goal_id: str) -> None:
    """Inspect one existing PUBLIC Build and explicitly review exact merge/cancel decisions."""
    from panestria.cli.build_tui import build_tui

    build_tui(config, goal_id)


def _service(config: Path) -> OwnerBuild:
    settings = load_build_settings(config)
    url = Settings(database_url=os.environ.get("PANESTRIA_DATABASE_URL", "")).validate_profile().database_url
    return OwnerBuild(settings, url.get_secret_value())


def _finish(operation: Callable[[], dict[str, Any]]) -> None:
    try:
        result = operation()
    except KeyboardInterrupt:
        typer.echo(json.dumps({"status": "UNAVAILABLE", "reason": "owner_build_interrupted_check_status"}))
        raise typer.Exit(130) from None
    except KernelDenied as exc:
        typer.echo(json.dumps({"status": "UNAVAILABLE", "reason": exc.code}))
        raise typer.Exit(1) from None
    except Exception:
        # Never echo config, database DSN, contract contents or native output.
        typer.echo(json.dumps({"status": "UNAVAILABLE", "reason": "owner_build_not_confirmed_check_status"}))
        raise typer.Exit(1) from None
    typer.echo(json.dumps(result, sort_keys=True))
    if result.get("status") in {"FAILED", "UNAVAILABLE", "CANCELLED"}:
        raise typer.Exit(1)


@build_app.command("prepare-policy")
def prepare_policy(config: Config, allow_public_native_build: bool = False) -> None:
    """Show a pending PUBLIC Build policy; do not approve it or call a model."""
    if not allow_public_native_build:
        raise typer.BadParameter("--allow-public-native-build is required")
    _finish(lambda: _service(config).prepare_policy())


@build_app.command("confirm-policy")
def confirm_policy(config: Config, review_id: str, effect_digest: str) -> None:
    """Approve the exact previously displayed policy digest as the local owner."""
    _finish(lambda: _service(config).confirm_policy(review_id, effect_digest))


@build_app.command("submit")
def submit(
    config: Config,
    contract: Annotated[Path, typer.Option("--contract")],
    selected_path: Annotated[list[str], typer.Option("--select")],
    expected_base: Annotated[str, typer.Option("--expected-base")],
    idempotency_key: Annotated[str, typer.Option("--idempotency-key")],
    public_subscription_run: bool = False,
) -> None:
    """Run one admitted PUBLIC Build and stop at independent review."""

    def run() -> dict[str, Any]:
        if public_subscription_run is not True:
            raise ValueError("explicit_public_build_intent_required")
        document = json.loads(read_private(contract, 64 * 1024))
        if not isinstance(document, dict):
            raise ValueError("invalid_build_contract")
        return _service(config).submit(
            document, tuple(selected_path), expected_base, idempotency_key, public_subscription_run=True
        )

    _finish(run)


@build_app.command("status")
def status(config: Config, goal_id: str, diff: bool = False) -> None:
    """Inspect canonical state, exact approval, independent checks and optional diff."""
    _finish(lambda: _service(config).status(goal_id, diff=diff))


@build_app.command("metrics")
def metrics(config: Config, goal_id: str) -> None:
    """Explicitly save a private derived runtime snapshot for a canonical Build goal."""
    _finish(lambda: _service(config).capture_metrics(goal_id))


@build_app.command("progress")
def progress(config: Config, goal_id: str) -> None:
    """Inspect canonical plan progress using the existing owner Build configuration."""
    _finish(lambda: _service(config).progress(goal_id))


@build_app.command("approve")
def approve(config: Config, approval_id: str, effect_digest: str, expected_version: int, idempotency_key: str) -> None:
    """Approve an exact candidate and dispatch its protected, revalidated Git CAS."""
    _finish(lambda: _service(config).approve(approval_id, effect_digest, expected_version, idempotency_key))


@build_app.command("cancel")
def cancel(config: Config, goal_id: str, expected_version: int) -> None:
    """Revoke current execution using the task version from status."""
    _finish(lambda: _service(config).cancel(goal_id, expected_version))
