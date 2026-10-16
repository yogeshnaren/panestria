"""Local CLI for health, goals, and exact approval decisions."""

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
from panestria.cli.approvals import approve_command, deny_command, list_command
from panestria.cli.ask import ask_command
from panestria.cli.goals import goal_app, show_artifact
from panestria.cli.local import local_app
from panestria.cli.native import native_app
from panestria.cli.profile import profile_app
from panestria.cli.quota import quota_app
from panestria.config import ProfileRejected, load_settings

app = typer.Typer(add_completion=False, no_args_is_help=True)
artifact_app = typer.Typer(no_args_is_help=True)
app.add_typer(goal_app, name="goal")
app.add_typer(artifact_app, name="artifact")
app.add_typer(native_app, name="native")
app.add_typer(profile_app, name="profile")
app.add_typer(quota_app, name="quota")
app.add_typer(local_app, name="local")
app.command("approve")(approve_command)
app.command("deny")(deny_command)
app.command("approvals")(list_command)
app.command("ask")(ask_command)


@artifact_app.command("show")
def artifact_show(
    artifact_id: str = typer.Argument(...),
    base_url: str = typer.Option(..., "--base-url"),
    token: str = typer.Option(..., "--token"),
) -> None:
    """Print one artifact hash and its check verdicts."""
    _status, body = show_artifact(base_url=base_url, token=token, artifact_id=artifact_id)
    typer.echo(json.dumps(body))


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


if __name__ == "__main__":
    app()
