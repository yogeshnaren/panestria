"""Approval CLI. The command prints the digest and does not hide a decision."""

from __future__ import annotations

import json
from urllib.request import Request

import typer

from panestria.cli.goals import Send, _default_send, _finish, loopback_base

_APPROVE_ID = typer.Argument(...)
_APPROVE_DIGEST = typer.Option(..., "--effect-digest")
_APPROVE_VERSION = typer.Option(..., "--expected-version")
_APPROVE_KEY = typer.Option(..., "--idempotency-key")
_APPROVE_BASE = typer.Option(..., "--base-url")
_APPROVE_TOKEN = typer.Option(..., "--token")
_DENY_ID = typer.Argument(...)
_DENY_DIGEST = typer.Option(..., "--effect-digest")
_DENY_VERSION = typer.Option(..., "--expected-version")
_DENY_KEY = typer.Option(..., "--idempotency-key")
_DENY_BASE = typer.Option(..., "--base-url")
_DENY_TOKEN = typer.Option(..., "--token")


def decide_approval(
    *,
    base_url: str,
    token: str,
    approval_id: str,
    effect_digest: str,
    expected_version: int,
    decision: str,
    idempotency_key: str,
    send: Send = _default_send,
) -> tuple[int, dict[str, object]]:
    base = loopback_base(base_url)
    body = json.dumps(
        {"decision": decision, "effect_digest": effect_digest, "expected_version": expected_version},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    request = Request(
        f"{base}/v1/approvals/{approval_id}/decision",
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


def list_approvals(
    *,
    base_url: str,
    token: str,
    send: Send = _default_send,
) -> tuple[int, dict[str, object]]:
    base = loopback_base(base_url)
    request = Request(
        f"{base}/v1/approvals",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    status, payload = send(request)
    return _finish(status, payload)


_LIST_BASE = typer.Option(..., "--base-url")
_LIST_TOKEN = typer.Option(..., "--token")


def list_command(
    base_url: str = _LIST_BASE,
    token: str = _LIST_TOKEN,
) -> None:
    """List pending approvals for this owner and project."""
    _status, body = list_approvals(base_url=base_url, token=token)
    typer.echo(json.dumps(body))


def approve_command(
    approval_id: str = _APPROVE_ID,
    effect_digest: str = _APPROVE_DIGEST,
    expected_version: int = _APPROVE_VERSION,
    idempotency_key: str = _APPROVE_KEY,
    base_url: str = _APPROVE_BASE,
    token: str = _APPROVE_TOKEN,
) -> None:
    """Approve one exact digest. A mismatched digest is not a decision."""
    _status, body = decide_approval(
        base_url=base_url,
        token=token,
        approval_id=approval_id,
        effect_digest=effect_digest,
        expected_version=expected_version,
        decision="approve",
        idempotency_key=idempotency_key,
    )
    typer.echo(json.dumps(body))


def deny_command(
    approval_id: str = _DENY_ID,
    effect_digest: str = _DENY_DIGEST,
    expected_version: int = _DENY_VERSION,
    idempotency_key: str = _DENY_KEY,
    base_url: str = _DENY_BASE,
    token: str = _DENY_TOKEN,
) -> None:
    """Deny one exact digest."""
    _status, body = decide_approval(
        base_url=base_url,
        token=token,
        approval_id=approval_id,
        effect_digest=effect_digest,
        expected_version=expected_version,
        decision="deny",
        idempotency_key=idempotency_key,
    )
    typer.echo(json.dumps(body))
