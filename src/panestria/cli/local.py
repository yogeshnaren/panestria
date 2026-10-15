"""Explicit local owner setup; model and key lifecycle are separate actions."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

import psycopg
import typer
from pydantic import ValidationError

from panestria.api.db import DatabaseUnavailable, open_database
from panestria.config import ProfileRejected, Settings
from panestria.config_local import LocalApplicationRejected, create_local_token
from panestria.contracts.inference import InferenceUnavailable
from panestria.kernel.errors import KernelDenied
from panestria.kernel.local_setup import LocalSetupIntent, LocalSetupService
from panestria.kernel.uow import UnitOfWork

local_app = typer.Typer(no_args_is_help=True)
_TOKEN_FILE = typer.Option(..., "--token-file")
_CONFIG_FILE = typer.Option(..., "--config")


@local_app.command("token-create")
def token_create(token_file: Path = _TOKEN_FILE) -> None:
    """Create local loopback authentication only, without displaying its value."""
    try:
        create_local_token(token_file)
    except LocalApplicationRejected as exc:
        typer.echo(json.dumps({"code": exc.code}), err=True)
        raise typer.Exit(2) from None
    typer.echo(json.dumps({"schema_version": 1, "status": "LOCAL_TOKEN_CREATED"}))


@local_app.command("serve")
def serve(config: Path = _CONFIG_FILE) -> None:
    """Run the foreground local Ask process; Ctrl+C stops its owned model."""
    from panestria.api.local_server import serve_local

    try:
        serve_local(config)
    except (LocalApplicationRejected, ProfileRejected, KernelDenied, InferenceUnavailable) as exc:
        code = exc.code
    except (DatabaseUnavailable, psycopg.Error, OSError, ValueError):
        code = "local_startup_failed"
    else:
        return
    typer.echo(json.dumps({"code": code}), err=True)
    raise typer.Exit(2)


@local_app.command("setup")
def setup(
    owner_id: str = typer.Option(..., "--owner-id"),
    project_id: str = typer.Option(..., "--project-id"),
    offline_ask: bool = typer.Option(False, "--offline-ask"),
) -> None:
    """Initialize an explicit read-only Ask scope; never modify existing policy."""
    try:
        if offline_ask is not True:
            raise KernelDenied("offline_ask_intent_required")
        intent = LocalSetupIntent(owner_id=owner_id, project_id=project_id, intent="OFFLINE_ASK")
        url = Settings(database_url=os.environ.get("PANESTRIA_DATABASE_URL", "")).validate_profile().database_url
        with open_database(url.get_secret_value()) as c:
            receipt = LocalSetupService().initialize(UnitOfWork(c), intent)
    except ValidationError:
        code = "invalid_local_setup"
    except ProfileRejected as exc:
        code = exc.code
    except KernelDenied as exc:
        code = exc.code
    except (DatabaseUnavailable, psycopg.Error):
        code = "database_unavailable"
    else:
        typer.echo(json.dumps({"schema_version": 1, "status": "CONFIGURED", **asdict(receipt)}))
        return
    typer.echo(json.dumps({"code": code}), err=True)
    raise typer.Exit(code=2)
