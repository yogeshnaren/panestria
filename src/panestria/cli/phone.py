"""Local owner controls; remote devices receive metadata-only sessions."""

import json
import os
from pathlib import Path
from typing import Annotated
from uuid import UUID

import psycopg
import typer

from panestria.api.db import DatabaseUnavailable, open_database
from panestria.api.phone import phone_service, serve_phone
from panestria.config import ProfileRejected, Settings
from panestria.config_local import LocalApplicationRejected
from panestria.config_phone import load_phone_settings
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork

phone_app = typer.Typer(no_args_is_help=True)


def _failed(exc: Exception) -> None:
    code = (
        exc.code if isinstance(exc, (LocalApplicationRejected, ProfileRejected, KernelDenied)) else "phone_unavailable"
    )
    typer.echo(json.dumps({"code": code}), err=True)
    raise typer.Exit(2)


@phone_app.command("serve")
def serve(config: Annotated[Path, typer.Option("--config")], assets: Annotated[Path, typer.Option("--assets")]) -> None:
    try:
        serve_phone(config, assets)
    except (LocalApplicationRejected, ProfileRejected, KernelDenied, OSError, ValueError) as exc:
        _failed(exc)


def _owner_action(config: Path, action: str, identity: UUID | None = None) -> None:
    try:
        settings, token = load_phone_settings(config)
        dsn = (
            Settings(database_url=os.environ.get("PANESTRIA_DATABASE_URL", ""))
            .validate_profile()
            .database_url.get_secret_value()
        )
        service = phone_service(settings, token.get_secret_value())
        actor = Actor(str(settings.owner_id), str(settings.project_id))
        with open_database(dsn) as connection:
            if action == "pair-code":
                code = service.issue_pairing_code(UnitOfWork(connection), actor)
                result: dict[str, object] = {"code": code, "expires_in_seconds": 120, "origin": settings.origin}
            elif action == "devices":
                result = {"devices": service.devices(UnitOfWork(connection), actor)}
            else:
                assert identity is not None
                service.revoke_device(UnitOfWork(connection), actor, str(identity))
                result = {"session_id": str(identity), "state": "REVOKED"}
        typer.echo(json.dumps(result))
    except (
        LocalApplicationRejected,
        ProfileRejected,
        KernelDenied,
        DatabaseUnavailable,
        psycopg.Error,
        OSError,
        ValueError,
    ) as exc:
        _failed(exc)


@phone_app.command("pair-code")
def pair_code(config: Annotated[Path, typer.Option("--config")]) -> None:
    _owner_action(config, "pair-code")


@phone_app.command("devices")
def devices(config: Annotated[Path, typer.Option("--config")]) -> None:
    _owner_action(config, "devices")


@phone_app.command("revoke")
def revoke(
    config: Annotated[Path, typer.Option("--config")],
    session_id: UUID,
    confirm: Annotated[bool, typer.Option("--confirm-revocation")] = False,
) -> None:
    if not confirm:
        _failed(KernelDenied("phone_revocation_confirmation_required"))
    _owner_action(config, "revoke", session_id)
