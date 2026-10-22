"""Explicit local owner setup; model and key lifecycle are separate actions."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import httpx2 as httpx
import psycopg
import typer
from pydantic import ValidationError

from panestria.api.db import DatabaseUnavailable, open_database
from panestria.cli.local_init import configured_message, first_run_files
from panestria.cli.tui_client import LocalAskClient, TerminalUnavailable
from panestria.config import ProfileRejected, Settings
from panestria.config_local import LocalApplicationRejected, create_local_token, load_local_settings
from panestria.contracts.inference import InferenceUnavailable
from panestria.contracts.model_manifest import ModelManifest
from panestria.kernel.errors import KernelDenied
from panestria.kernel.local_setup import LocalSetupIntent, LocalSetupService
from panestria.kernel.uow import UnitOfWork

local_app = typer.Typer(no_args_is_help=True)
_TOKEN_FILE = typer.Option(..., "--token-file")
_CONFIG_FILE = typer.Option(..., "--config")
_MANIFEST_OUTPUT = typer.Option(..., "--output")


@local_app.command("model-manifest")
def model_manifest(
    config: Path = _CONFIG_FILE,
    output: Path = _MANIFEST_OUTPUT,
    json_output: bool = typer.Option(False, "--json-output"),
) -> None:
    """Save public identity from your running pinned Ask; no inference or qualification."""
    try:
        if not output.is_absolute() or output.resolve() != output or not output.parent.is_dir():
            raise ValueError
        settings, _ = load_local_settings(config)
        if output.is_relative_to(settings.model_cache) or output.is_relative_to(settings.runtime_directory):
            raise ValueError
        body = LocalAskClient(config).status().get("model_manifest")
        descriptor = ModelManifest.model_validate_json(json.dumps(body))
        if json_output:
            descriptor = descriptor.for_json_output()
        raw = (descriptor.model_dump_json(indent=2) + "\n").encode()
        descriptor_fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor_fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except (LocalApplicationRejected, TerminalUnavailable) as exc:
        code = exc.code
    except (OSError, ValueError):
        code = "model_manifest_export_unavailable"
    else:
        typer.echo(json.dumps({
            "status": "EXPECTED_MODEL_MANIFEST_WRITTEN", "sha256": descriptor.sha256(),
            "qualification": "NOT_EVALUATED", "inference_started": False,
        }))
        return
    typer.echo(json.dumps({"code": code, "existing_files_preserved": True}), err=True)
    raise typer.Exit(2)


@local_app.command("init")
def initialize(
    directory: Annotated[Path, typer.Option("--directory")],
    model_cache: Annotated[Path, typer.Option("--model-cache")],
    port: Annotated[int, typer.Option("--port")] = 8768,
    offline_ask: Annotated[bool, typer.Option("--offline-ask")] = False,
) -> None:
    """Prepare private Ask settings and stable IDs; use an already migrated database."""
    try:
        if not offline_ask:
            raise KernelDenied("offline_ask_intent_required")
        url = Settings(database_url=os.environ.get("PANESTRIA_DATABASE_URL", "")).validate_profile().database_url
        with first_run_files(directory, model_cache, port) as config:
            from panestria.api.local_server import SCHEMA_HEAD

            with open_database(url.get_secret_value()) as c:
                if c.execute("SELECT version_num FROM alembic_version").fetchone() != (SCHEMA_HEAD,):
                    raise LocalApplicationRejected("database_schema_not_current")
                intent = LocalSetupIntent(owner_id=config.owner_id, project_id=config.project_id, intent="OFFLINE_ASK")
                receipt = LocalSetupService().initialize(UnitOfWork(c), intent)
        # The connection context has committed before claiming CONFIGURED.
        typer.echo(configured_message(directory, asdict(receipt)))
        return
    except (LocalApplicationRejected, ProfileRejected, KernelDenied) as exc:
        code = exc.code
    except psycopg.errors.UndefinedTable:
        code = "database_schema_not_current"
    except (DatabaseUnavailable, psycopg.Error):
        code = "database_unavailable"
    except (OSError, ValueError):
        code = "local_initialization_unavailable"
    typer.echo(json.dumps({"code": code, "files_preserved": True}), err=True)
    raise typer.Exit(2)


@local_app.command("pair-code")
def pair_code(config: Path = _CONFIG_FILE) -> None:
    """Print a short one-use browser code; never print the local bearer token."""
    try:
        settings, token = load_local_settings(config)
        with httpx.Client(trust_env=False, follow_redirects=False, timeout=5) as client:
            with client.stream(
                "POST",
                settings.origin + "/v1/session/code",
                json={},
                headers={"Authorization": "Bearer " + token.get_secret_value()},
            ) as response:
                data = bytearray()
                for chunk in response.iter_bytes():
                    if len(data) + len(chunk) > 4096:
                        raise LocalApplicationRejected("local_pairing_unavailable")
                    data.extend(chunk)
                body = json.loads(data)
        if (
            response.status_code != 200
            or not isinstance(body, dict)
            or re.fullmatch(r"[0-9A-F]{8}", str(body.get("code"))) is None
        ):
            raise LocalApplicationRejected("local_pairing_unavailable")
        typer.echo(json.dumps({"code": body["code"], "expires_in_seconds": 120, "origin": settings.origin}))
    except LocalApplicationRejected as exc:
        typer.echo(json.dumps({"code": exc.code}), err=True)
        raise typer.Exit(2) from None
    except (ValueError, OSError, httpx.HTTPError):
        typer.echo(json.dumps({"code": "local_pairing_unavailable"}), err=True)
        raise typer.Exit(2) from None


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
def serve(
    config: Path = _CONFIG_FILE,
    mission_assets: Annotated[Path | None, typer.Option("--mission-assets")] = None,
) -> None:
    """Run the foreground local Ask process; Ctrl+C stops its owned model."""
    from panestria.api.local_server import serve_local

    try:
        serve_local(config, mission_assets=mission_assets)
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
