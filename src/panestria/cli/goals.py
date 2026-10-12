"""Goal CLI. Requests go to a loopback API and do not approve anything."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import typer

from panestria.api.auth import MAX_BODY_BYTES

goal_app = typer.Typer(no_args_is_help=True)
_LOOPBACK = frozenset({"127.0.0.1", "localhost"})
_CONTRACT = typer.Option(..., "--contract", exists=True, dir_okay=False)
_KEY = typer.Option(..., "--idempotency-key")
_SUBMIT_BASE = typer.Option(..., "--base-url")
_SUBMIT_TOKEN = typer.Option(..., "--token")
_STATUS_GOAL = typer.Argument(...)
_STATUS_BASE = typer.Option(..., "--base-url")
_STATUS_TOKEN = typer.Option(..., "--token")
_EVENTS_GOAL = typer.Argument(...)
_AFTER = typer.Option("0", "--after")
_EVENTS_BASE = typer.Option(..., "--base-url")
_EVENTS_TOKEN = typer.Option(..., "--token")
Send = Callable[[Request], tuple[int, bytes]]


def loopback_base(base_url: str) -> str:
    parts = urlsplit(base_url)
    if parts.scheme != "http" or parts.hostname not in _LOOPBACK:
        raise typer.Exit(code=2)
    return base_url.rstrip("/")


def _default_send(request: Request) -> tuple[int, bytes]:
    try:
        with urlopen(request, timeout=5) as response:
            return int(response.status), response.read()
    except HTTPError as exc:
        return int(exc.code), exc.read()


def submit_contract(
    *,
    base_url: str,
    token: str,
    contract_path: Path,
    idempotency_key: str,
    send: Send = _default_send,
) -> tuple[int, dict[str, object]]:
    base = loopback_base(base_url)
    body = contract_path.read_bytes()
    if len(body) > MAX_BODY_BYTES:
        raise typer.Exit(code=1)
    request = Request(
        f"{base}/v1/goals",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
        },
        method="POST",
    )
    status, payload = send(request)
    return _finish(status, payload)


def read_status(
    *,
    base_url: str,
    token: str,
    goal_id: str,
    send: Send = _default_send,
) -> tuple[int, dict[str, object]]:
    base = loopback_base(base_url)
    request = Request(
        f"{base}/v1/goals/{goal_id}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    status, payload = send(request)
    return _finish(status, payload)


def read_events(
    *,
    base_url: str,
    token: str,
    goal_id: str,
    after: str,
    send: Send = _default_send,
) -> tuple[int, dict[str, object]]:
    base = loopback_base(base_url)
    request = Request(
        f"{base}/v1/goals/{goal_id}/events?after={after}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    status, payload = send(request)
    return _finish(status, payload)


def _finish(status: int, payload: bytes) -> tuple[int, dict[str, object]]:
    loaded = json.loads(payload)
    if not isinstance(loaded, dict):
        raise typer.Exit(code=1)
    if status >= 400:
        typer.echo(json.dumps(loaded), err=True)
        raise typer.Exit(code=1)
    return status, loaded


@goal_app.command("submit")
def submit_command(
    contract: Path = _CONTRACT,
    idempotency_key: str = _KEY,
    base_url: str = _SUBMIT_BASE,
    token: str = _SUBMIT_TOKEN,
) -> None:
    """Submit a contract file. The response includes whether the call replayed."""
    _status, body = submit_contract(
        base_url=base_url,
        token=token,
        contract_path=contract,
        idempotency_key=idempotency_key,
    )
    typer.echo(json.dumps(body))


@goal_app.command("status")
def status_command(
    goal_id: str = _STATUS_GOAL,
    base_url: str = _STATUS_BASE,
    token: str = _STATUS_TOKEN,
) -> None:
    """Print the scoped goal status."""
    _status, body = read_status(base_url=base_url, token=token, goal_id=goal_id)
    typer.echo(json.dumps(body))


@goal_app.command("events")
def events_command(
    goal_id: str = _EVENTS_GOAL,
    after: str = _AFTER,
    base_url: str = _EVENTS_BASE,
    token: str = _EVENTS_TOKEN,
) -> None:
    """Print events after a decimal sequence cursor."""
    _status, body = read_events(base_url=base_url, token=token, goal_id=goal_id, after=after)
    typer.echo(json.dumps(body))
