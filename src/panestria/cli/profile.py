"""Explicit local OS-key setup; commands never output key material."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import typer
from pydantic import ValidationError

from panestria.memory.keys import KeyStoreUnavailable, ProfileKeyHandle, SecretServiceProfileKeys

profile_app = typer.Typer(no_args_is_help=True)
_CONFIG_OPTION = typer.Option(..., "--config")
_SELECTION_OPTION = typer.Option(..., "--selection")
_DIRECTORY_OPTION = typer.Option(..., "--directory")
_CACHE_OPTION = typer.Option(..., "--model-cache")


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


@profile_app.command("style-tui")
def style_terminal(
    config: Path = _CONFIG_OPTION,
    profile_id: str = typer.Option(..., "--profile-id"),
    key_id: str | None = typer.Option(None, "--key-id"),
    expected_version: int | None = typer.Option(None, "--expected-version", min=0),
    owner_review: bool = typer.Option(False, "--owner-review"),
    examples_file: Path | None = typer.Option(None, "--examples-file"),
) -> None:
    """Edit structured preferences through an already enabled owner API; no inference."""
    from panestria.cli.profile_style import run_style_terminal
    from panestria.cli.tui_client import TerminalUnavailable
    from panestria.config_local import LocalApplicationRejected

    try:
        if examples_file is None:
            run_style_terminal(config, profile_id, key_id, expected_version, owner_review)
        else:
            run_style_terminal(config, profile_id, key_id, expected_version, owner_review, examples_file)
    except (TerminalUnavailable, LocalApplicationRejected) as error:
        typer.echo(json.dumps({"code": error.code}), err=True)
        raise typer.Exit(2) from None
    except (ValueError, OSError):
        typer.echo(json.dumps({"code": "profile_style_unavailable"}), err=True)
        raise typer.Exit(2) from None


@profile_app.command("ask-tui")
def profile_ask(
    config: Path = _CONFIG_OPTION,
    selection: Path = _SELECTION_OPTION,
    restricted_offline: bool = typer.Option(False, "--restricted-offline"),
) -> None:
    """Use one explicitly pinned approved profile selection for offline Ask."""
    from panestria.cli.profile_ask import profile_ask_terminal
    from panestria.cli.tui_client import TerminalUnavailable

    try:
        profile_ask_terminal(config, selection, restricted_offline)
    except TerminalUnavailable as error:
        typer.echo(json.dumps({"code": error.code}), err=True)
        raise typer.Exit(2) from None


@profile_app.command("qualify")
def qualify_runtime(
    directory: Path = _DIRECTORY_OPTION,
    model_cache: Path = _CACHE_OPTION,
    synthetic_local_smoke: bool = typer.Option(False, "--synthetic-local-smoke"),
) -> None:
    """Explicit actual isolated OS-key and existing CPU model checks; no owner data."""
    from panestria.execution.native_qualification import QualificationUnavailable
    from panestria.execution.profile_qualification import qualify_profiles
    from panestria.execution.proposal_demo import DemoUnavailable
    from panestria.kernel.errors import KernelDenied

    try:
        result = qualify_profiles(directory, model_cache, synthetic_local_smoke=synthetic_local_smoke)
        typer.echo(json.dumps(result))
        if result["status"] != "PASS":
            raise typer.Exit(2)
    except QualificationUnavailable as error:
        typer.echo(json.dumps({"code": str(error)}), err=True)
        raise typer.Exit(2) from None
    except DemoUnavailable:
        typer.echo(json.dumps({"code": "private_profile_qualification_directory_unavailable"}), err=True)
        raise typer.Exit(2) from None
    except (KeyStoreUnavailable, KernelDenied) as error:
        typer.echo(json.dumps({"code": error.code}), err=True)
        raise typer.Exit(2) from None
    except (OSError, ValueError):
        typer.echo(json.dumps({"code": "profile_qualification_unavailable"}), err=True)
        raise typer.Exit(2) from None


@profile_app.command("serve")
def serve_profiles(
    config: Path = _CONFIG_OPTION,
    restricted_offline: bool = typer.Option(False, "--restricted-offline"),
) -> None:
    """Start explicit qualified profile/Ask service; preserve busy services and keys."""
    from panestria.api.profile_server import serve_profiles as serve
    from panestria.config import ProfileRejected
    from panestria.config_local import LocalApplicationRejected
    from panestria.contracts.inference import InferenceUnavailable
    from panestria.kernel.errors import KernelDenied

    try:
        serve(config, restricted_offline=restricted_offline)
    except (
        KeyStoreUnavailable,
        LocalApplicationRejected,
        ProfileRejected,
        InferenceUnavailable,
        KernelDenied,
    ) as error:
        typer.echo(json.dumps({"code": error.code}), err=True)
        raise typer.Exit(2) from None
    except (ValueError, OSError):
        typer.echo(json.dumps({"code": "profile_service_unavailable"}), err=True)
        raise typer.Exit(2) from None
