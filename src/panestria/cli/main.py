"""Local CLI. Domain commands are not part of this slice."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import typer

from panestria import package_version
from panestria.api.health import (
    HealthService,
    SecretBearingOutputRejected,
    default_readiness_probe,
    secret_rejection_body,
)
from panestria.config import ProfileRejected, load_settings

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(package_version())
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Print the installed package version.",
    ),
) -> None:
    """Panestria local process commands."""


@app.command("version")
def version_command() -> None:
    """Print the installed package version."""
    typer.echo(package_version())


@app.command("health")
def health_command() -> None:
    """Print bounded readiness. Exit 1 when the process is not ready."""
    service: HealthService | None = None
    try:
        try:
            settings = load_settings()
        except ProfileRejected as exc:
            typer.echo(
                json.dumps({"code": exc.code, "message": exc.message, "retryable": False}),
                err=True,
            )
            raise typer.Exit(code=2) from None
        service = HealthService(settings, default_readiness_probe)
        deadline = datetime.now(timezone.utc) + timedelta(milliseconds=settings.readiness_budget_ms)
        try:
            body = service.readiness(deadline)
        except SecretBearingOutputRejected:
            typer.echo(secret_rejection_body(str(uuid4())).model_dump_json(), err=True)
            raise typer.Exit(code=1) from None
        typer.echo(body.model_dump_json())
        if body.status != "ready":
            raise typer.Exit(code=1)
    finally:
        if service is not None:
            service.shutdown()
