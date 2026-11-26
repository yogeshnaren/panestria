"""The owner app: ``panestria serve`` and its per-scope browser pairing codes."""

from __future__ import annotations

import json
import re
from enum import Enum
from pathlib import Path
from typing import Annotated

import httpx2 as httpx
import psycopg
import typer

from panestria.api.db import DatabaseUnavailable
from panestria.config import ProfileRejected
from panestria.config_local import LocalApplicationRejected, load_local_settings
from panestria.contracts.inference import InferenceUnavailable
from panestria.kernel.errors import KernelDenied

_CONFIG = typer.Option("--config", help="The local Ask configuration (local.json): owner, project, token and port.")


class Scope(str, Enum):
    activity = "activity"
    ask = "ask"
    build = "build"


def serve_command(
    config: Annotated[Path, _CONFIG],
    build_config: Annotated[
        Path | None,
        typer.Option("--build-config", help="Private Build configuration; adds Build review, plans and runs."),
    ] = None,
    assets: Annotated[
        Path | None,
        typer.Option("--assets", help="A Mission Control build directory; defaults to the packaged one."),
    ] = None,
) -> None:
    """Run Ask, Mission Control and, with a Build configuration, Build on one port; Ctrl+C stops its model."""
    from panestria.api.owner import serve_owner

    try:
        serve_owner(config, build_run=build_config, assets=assets)
    except (LocalApplicationRejected, ProfileRejected, KernelDenied, InferenceUnavailable) as exc:
        code = exc.code
    except (DatabaseUnavailable, psycopg.Error, OSError, ValueError):
        code = "local_startup_failed"
    else:
        return
    typer.echo(json.dumps({"code": code}), err=True)
    raise typer.Exit(2)


def pair_code_command(
    config: Annotated[Path, _CONFIG],
    scope: Annotated[Scope, typer.Option("--scope", help="The session to pair: activity, ask or build.")],
) -> None:
    """Print a one-use browser code for one session scope; never print the bearer token."""
    try:
        settings, token = load_local_settings(config)
        with httpx.Client(trust_env=False, follow_redirects=False, timeout=5) as client:
            with client.stream(
                "POST",
                f"{settings.origin}/v1/session/{scope.value}/code",
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
        typer.echo(
            json.dumps(
                {"code": body["code"], "scope": scope.value, "expires_in_seconds": 120, "origin": settings.origin}
            )
        )
        return
    except LocalApplicationRejected as exc:
        code = exc.code
    except (ValueError, OSError, httpx.HTTPError):
        code = "local_pairing_unavailable"
    typer.echo(json.dumps({"code": code}), err=True)
    raise typer.Exit(2)
