"""Owner declaration setup, review and revoke; no runtime connector activation."""

import json
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer

from panestria.cli.activity import initialize
from panestria.cli.connection_client import ConnectionClient
from panestria.cli.tui_client import TerminalUnavailable
from panestria.config_local import LocalApplicationRejected, read_private
from panestria.contracts.connections import ConnectionReviewRequest, SubmitReview, parse_connection_contract

connections_app = typer.Typer(no_args_is_help=True)
connections_app.command("init")(initialize)  # Same private owner/project format; no duplicate setup implementation.


@connections_app.command("serve")
def serve(config: Annotated[Path, typer.Option("--config")]) -> None:
    """Run a foreground metadata/declaration API only; no model, worker or connector."""
    from panestria.api.activity_server import serve_activity
    from panestria.config import ProfileRejected

    try:
        serve_activity(config, connection_reviews=True)
    except ProfileRejected as error:
        failed(LocalApplicationRejected(error.code))
    except (LocalApplicationRejected, TerminalUnavailable, ValueError, TypeError) as error:
        failed(error)


@connections_app.command("scope")
def scope(config: Annotated[Path, typer.Option("--config")]) -> None:
    """Show the current project policy reference for an explicit declaration request."""
    try:
        typer.echo(ConnectionClient(config).scope().model_dump_json())
    except (LocalApplicationRejected, TerminalUnavailable, ValueError, TypeError) as error:
        failed(error)


def failed(error: Exception) -> None:
    code = (
        error.code if isinstance(error, (LocalApplicationRejected, TerminalUnavailable)) else "connection_input_invalid"
    )
    typer.echo(json.dumps({"code": code, "runtime_available": False}), err=True)
    raise typer.Exit(2)


@connections_app.command("propose")
def propose(
    config: Annotated[Path, typer.Option("--config")],
    request_file: Annotated[Path, typer.Option("--request-file")],
) -> None:
    """Retain one exact private request; never approve it or connect anything."""
    try:
        if not request_file.is_absolute() or request_file.resolve() != request_file:
            raise LocalApplicationRejected("connection_request_path_invalid")
        request = parse_connection_contract(SubmitReview, read_private(request_file, 65536))
        result = ConnectionClient(config).propose(request)
        typer.echo(result.model_dump_json())
    except (LocalApplicationRejected, TerminalUnavailable, ValueError, TypeError, RecursionError) as error:
        failed(error)


@connections_app.command("show")
def show(
    config: Annotated[Path, typer.Option("--config")], grant_id: Annotated[UUID, typer.Option("--grant-id")]
) -> None:
    """Inspect current declaration and stale/revoked/expiry state without dispatch."""
    try:
        typer.echo(ConnectionClient(config).current(str(grant_id)).model_dump_json())
    except (LocalApplicationRejected, TerminalUnavailable, ValueError, TypeError) as error:
        failed(error)


@connections_app.command("revoke")
def revoke(
    config: Annotated[Path, typer.Option("--config")],
    grant_id: Annotated[UUID, typer.Option("--grant-id")],
    task_id: Annotated[UUID, typer.Option("--task-id")],
    proposal_id: Annotated[UUID, typer.Option("--proposal-id")],
) -> None:
    """Propose revocation of the current exact version; separate owner review required."""
    try:
        client = ConnectionClient(config)
        source = client.current(str(grant_id))
        policy = client.scope()
        request = SubmitReview(
            schema_version=1,
            task_id=str(task_id),
            change=ConnectionReviewRequest(
                proposal_id=str(proposal_id),
                grant_id=source.grant_id,
                expected_version=source.version,
                policy_ref=policy.policy_ref,
                operation="REVOKE",
                manifest=None,
            ),
        )
        typer.echo(client.propose(request).model_dump_json())
    except (LocalApplicationRejected, TerminalUnavailable, ValueError, TypeError) as error:
        failed(error)


@connections_app.command("review")
def review(
    config: Annotated[Path, typer.Option("--config")], proposal_id: Annotated[UUID, typer.Option("--proposal-id")]
) -> None:
    """Review every declared scope, then separately confirm one exact decision."""
    from panestria.cli.connection_terminal import run_connection_terminal

    try:
        run_connection_terminal(config, str(proposal_id))
    except (LocalApplicationRejected, TerminalUnavailable, ValueError, TypeError) as error:
        failed(error)


@connections_app.command("prepare-public-fetch")
def prepare_public_fetch(
    config: Annotated[Path, typer.Option("--config")],
    research_config: Annotated[Path, typer.Option("--research-config")],
    task_id: Annotated[UUID, typer.Option("--task-id")],
    proposal_id: Annotated[UUID, typer.Option("--proposal-id")],
    origin: Annotated[list[str], typer.Option("--origin")],
    output: Annotated[Path, typer.Option("--output")],
    max_calls: Annotated[int, typer.Option(min=1, max=10000)] = 16,
    max_bytes: Annotated[int, typer.Option(min=49155, max=64 * 1024 * 1024)] = 8 * 1024 * 1024,
    max_wall_seconds: Annotated[int, typer.Option(min=1, max=3600)] = 3600,
    expires_seconds: Annotated[int, typer.Option(min=1, max=30 * 86400)] = 3600,
) -> None:
    """Write one unverified anonymous GET declaration for separate exact owner review."""
    from datetime import UTC, datetime, timedelta

    from panestria.cli.research import _write_private
    from panestria.config_research import load_research_settings
    from panestria.contracts.connections import ConnectionBudget, ConnectionManifest
    from panestria.contracts.fetch_connection import (
        FETCH_CONFIGURATION_SHA256,
        FETCH_CONNECTOR,
        FETCH_CONNECTOR_VERSION,
        HTTP_HOP_RESERVED_BYTES,
        anonymous_fetch_account,
    )

    try:
        settings = load_research_settings(research_config)
        scope = ConnectionClient(config).scope()
        if (scope.owner_id, scope.project_id) != (str(settings.owner_id), str(settings.project_id)):
            raise LocalApplicationRejected("connection_scope_mismatch")
        manifest = ConnectionManifest(
            owner_id=scope.owner_id,
            project_id=scope.project_id,
            connector_ref=FETCH_CONNECTOR,
            connector_version=FETCH_CONNECTOR_VERSION,
            configuration_sha256=FETCH_CONFIGURATION_SHA256,
            account_ref=anonymous_fetch_account(scope.owner_id, scope.project_id, FETCH_CONFIGURATION_SHA256),
            actions=("read", "send"),
            data_classes=("PUBLIC",),
            origins=tuple(origin),
            budget=ConnectionBudget(max_calls=max_calls, max_bytes=max_bytes, max_wall_seconds=max_wall_seconds),
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_seconds),
            conformance_sha256=settings.certificate_sha256,
        )
        request = SubmitReview(
            schema_version=1,
            task_id=str(task_id),
            change=ConnectionReviewRequest(
                proposal_id=str(proposal_id),
                policy_ref=scope.policy_ref,
                expected_version=0,
                operation="REPLACE",
                manifest=manifest,
            ),
        )
        _write_private(output, request.model_dump_json().encode() + b"\n")
        typer.echo(
            json.dumps(
                {
                    "status": "TEMPLATE_CREATED_UNVERIFIED",
                    "proposal_id": str(proposal_id),
                    "runtime_available": False,
                    "http_hop_capacity_reservation_bytes": HTTP_HOP_RESERVED_BYTES,
                    "actual_wire_usage": "NOT_MEASURED",
                    "account_identity": "ANONYMOUS_SERVICE_NOT_AUTHENTICATED_ACCOUNT",
                }
            )
        )
    except (Exception, KeyboardInterrupt):
        failed(LocalApplicationRejected("public_fetch_declaration_template_unavailable"))
