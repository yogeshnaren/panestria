"""Explicit local OS-key setup; commands never output key material."""

from __future__ import annotations

import json
from uuid import uuid4

import typer
from pydantic import ValidationError

from panestria.memory.keys import KeyStoreUnavailable, ProfileKeyHandle, SecretServiceProfileKeys

profile_app = typer.Typer(no_args_is_help=True)


def _operation(owner_id: str, project_id: str, profile_id: str, key_id: str, *, create: bool) -> None:
    try:
        handle = ProfileKeyHandle(owner_id=owner_id, project_id=project_id, profile_id=profile_id, key_id=key_id)
        store = SecretServiceProfileKeys()
        if create:
            store.provision(handle)
        else:
            store.load(handle)
    except ValidationError:
        typer.echo(json.dumps({"code": "invalid_profile_key_handle"}), err=True)
        raise typer.Exit(code=2) from None
    except KeyStoreUnavailable as exc:
        # Retain the opaque intent identity if creation's outcome is unknown.
        # The operator can check that exact handle instead of creating a new one.
        typer.echo(json.dumps({"code": exc.code, "handle": handle.model_dump()}), err=True)
        raise typer.Exit(code=2) from None
    typer.echo(json.dumps({"schema_version": 1, "status": "PRESENT", "handle": handle.model_dump()}))


@profile_app.command("key-create")
def create_key(
    owner_id: str = typer.Option(..., "--owner-id"),
    project_id: str = typer.Option(..., "--project-id"),
    profile_id: str | None = typer.Option(None, "--profile-id"),
    key_id: str | None = typer.Option(None, "--key-id"),
) -> None:
    """Create a scoped OS key explicitly; retain its opaque handle, never its value."""
    _operation(owner_id, project_id, profile_id or str(uuid4()), key_id or str(uuid4()), create=True)


@profile_app.command("key-check")
def check_key(
    owner_id: str = typer.Option(..., "--owner-id"),
    project_id: str = typer.Option(..., "--project-id"),
    profile_id: str = typer.Option(..., "--profile-id"),
    key_id: str = typer.Option(..., "--key-id"),
) -> None:
    """Check an existing scoped handle; never provision, unlock or print a key."""
    _operation(owner_id, project_id, profile_id, key_id, create=False)
