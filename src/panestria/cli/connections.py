"""Owner declaration setup, review and revoke; no runtime connector activation."""

import json
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer

from panestria.cli.connection_client import ConnectionClient
from panestria.cli.tui_client import TerminalUnavailable
from panestria.config_local import LocalApplicationRejected, read_private
from panestria.contracts.connections import ConnectionReviewRequest, SubmitReview, parse_connection_contract

connections_app = typer.Typer(no_args_is_help=True)


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
    typer.echo(json.dumps({"code": code, "decision": "UNCONFIRMED", "runtime_available": False}), err=True)
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
