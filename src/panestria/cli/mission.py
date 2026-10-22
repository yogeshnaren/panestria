"""Explicit local browser modes; private operator settings determine capability."""

import json
import re
from pathlib import Path
from typing import Annotated

import httpx2 as httpx
import typer

from panestria.config import ProfileRejected
from panestria.config_activity import load_activity_settings
from panestria.config_local import LocalApplicationRejected

mission_app = typer.Typer(no_args_is_help=True)


@mission_app.command("serve")
def serve(
    config: Annotated[Path, typer.Option("--config")],
    assets: Annotated[Path, typer.Option("--assets")],
    build_evidence_store: Annotated[Path | None, typer.Option("--build-evidence-store")] = None,
    build_review_root: Annotated[
        Path | None,
        typer.Option(
            "--build-review-root", help="Explicit PUBLIC diff/report review and consent recording; no merge dispatch."
        ),
    ] = None,
    research_intake: Annotated[
        Path | None, typer.Option("--research-intake", help="Explicit PUBLIC question staging; no execution.")
    ] = None,
    build_intake: Annotated[
        bool, typer.Option("--build-intake", help="Explicit PUBLIC zero-cash plan staging; no acceptance or execution.")
    ] = False,
    build_plan_review: Annotated[
        bool, typer.Option("--build-plan-review", help="Explicit PUBLIC plan intake/review/acceptance; no execution.")
    ] = False,
    build_run: Annotated[
        Path | None,
        typer.Option("--build-run", help="Existing private Build config: explicit finite PUBLIC subscription runs."),
    ] = None,
) -> None:
    """Serve an explicit production dashboard build on the configured exclusive port."""
    from panestria.api.activity_server import serve_activity
    from panestria.kernel.errors import KernelDenied

    try:
        serve_activity(
            config,
            dashboard_assets=assets,
            build_evidence_store=build_evidence_store,
            build_review_root=build_review_root,
            research_intake=research_intake,
            build_intake=build_intake,
            build_plan_review=build_plan_review,
            build_run=build_run,
        )
        return
    except (LocalApplicationRejected, ProfileRejected, KernelDenied) as exc:
        code = exc.code
    except (OSError, ValueError):
        code = "mission_startup_failed"
    typer.echo(json.dumps({"code": code}), err=True)
    raise typer.Exit(2)


@mission_app.command("pair-code")
def pair_code(config: Annotated[Path, typer.Option("--config")]) -> None:
    """Issue one short code from the running dashboard; never disclose its bearer."""
    try:
        settings, token = load_activity_settings(config)
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
                        raise LocalApplicationRejected("mission_pairing_unavailable")
                    data.extend(chunk)
                body = json.loads(data)
        if (
            response.status_code != 200
            or not isinstance(body, dict)
            or re.fullmatch(r"[0-9A-F]{8}", str(body.get("code"))) is None
        ):
            raise LocalApplicationRejected("mission_pairing_unavailable")
        typer.echo(json.dumps({"code": body["code"], "expires_in_seconds": 120, "origin": settings.origin}))
        return
    except LocalApplicationRejected as exc:
        code = exc.code
    except (ValueError, OSError, httpx.HTTPError):
        code = "mission_pairing_unavailable"
    typer.echo(json.dumps({"code": code}), err=True)
    raise typer.Exit(2)
