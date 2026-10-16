"""Bounded owner metadata client; no provider login, scraping or background worker."""

from __future__ import annotations

import ipaddress
import json
import os
import re
import stat
from pathlib import Path
from urllib.parse import urlsplit

import httpx2 as httpx
import typer
from pydantic import ValidationError

from panestria.contracts.quota import QueryQuota, QuotaId, QuotaObservation, QuotaScope, SubmitQuota

quota_app = typer.Typer(no_args_is_help=True)
_TOKEN = typer.Option(..., "--token-file")
_INPUT = typer.Option(..., "--input-file")
_BASE = typer.Option("http://127.0.0.1:8766", "--base-url")


def _read(path: Path, *, private: bool, limit: int) -> bytes:
    path = path.absolute()
    if path.resolve() != path:
        raise ValueError("noncanonical_input")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
            or not 1 <= info.st_size <= limit
            or info.st_mode & (0o077 if private else 0o022)
        ):
            raise ValueError("unsafe_input")
        content = os.read(descriptor, limit + 1)
        after = os.fstat(descriptor)
        if len(content) != info.st_size or (info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ValueError("changed_input")
        return content
    finally:
        os.close(descriptor)


def _base(value: str) -> str:
    parts = urlsplit(value)
    if (
        parts.scheme != "http"
        or not parts.hostname
        or parts.port is None
        or parts.path
        or parts.query
        or parts.fragment
        or parts.username is not None
        or parts.password is not None
    ):
        raise ValueError("invalid_loopback")
    # Never resolve a DNS hostname, including localhost, using inherited DNS.
    address = ipaddress.ip_address(parts.hostname)
    if not address.is_loopback or not 1 <= parts.port <= 65535:
        raise ValueError("invalid_loopback")
    host = f"[{address}]" if address.version == 6 else str(address)
    return f"http://{host}:{parts.port}"


def _request(base: str, token_file: Path, method: str, path: str, body: dict[str, object] | None) -> object:
    origin = _base(base)
    token = _read(token_file, private=True, limit=256).decode("ascii").strip()
    if re.fullmatch(r"[A-Za-z0-9._~+/=-]{16,256}", token) is None:
        raise ValueError("invalid_token")
    with httpx.Client(trust_env=False, follow_redirects=False, timeout=5) as client:
        with client.stream(method, origin + path, json=body, headers={"Authorization": "Bearer " + token}) as response:
            chunks, total = [], 0
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > 32768:
                    raise ValueError("response_limit")
                chunks.append(chunk)
            if response.status_code not in {200, 201}:
                # Never echo a remote error/body, token, path or exception text.
                raise ValueError("api_denied")
    return json.loads(b"".join(chunks))


def _safe_view(value: object) -> dict[str, object]:
    # Print only a closed quota report and the server's bounded display fields.
    # Drop arbitrary server strings rather than trusting remote JSON for output.
    if not isinstance(value, dict) or value.get("authority") != "OBSERVATION_ONLY":
        raise ValueError("invalid_quota_response")
    observation = QuotaObservation.model_validate_json(json.dumps(value.get("observation")))
    fresh, confidence, remaining = value.get("freshness"), value.get("confidence"), value.get("effective_remaining")
    if (
        not isinstance(fresh, str)
        or not isinstance(confidence, str)
        or fresh not in {"FRESH", "STALE", "RESET_PASSED"}
        or confidence not in {"REPORTED", "ESTIMATED", "UNKNOWN"}
    ):
        raise ValueError("invalid_quota_response")
    expected = (
        "UNKNOWN"
        if fresh != "FRESH" or observation.remaining is None or observation.source == "UNKNOWN"
        else "ESTIMATED"
        if observation.source == "ESTIMATED"
        else "REPORTED"
    )
    if confidence != expected:
        raise ValueError("invalid_quota_response")
    if (confidence == "UNKNOWN" and remaining is not None) or (
        confidence != "UNKNOWN" and (fresh != "FRESH" or remaining != observation.remaining or remaining is None)
    ):
        raise ValueError("invalid_quota_response")
    return {
        "observation": observation.model_dump(mode="json"),
        "freshness": fresh,
        "confidence": confidence,
        "effective_remaining": remaining,
        "authority": "OBSERVATION_ONLY",
    }


def _failure() -> None:
    typer.echo("quota_input_or_api_unavailable", err=True)
    raise typer.Exit(2)


@quota_app.command("report")
def report_quota(
    input_file: Path = _INPUT,
    token_file: Path = _TOKEN,
    base_url: str = _BASE,
) -> None:
    """Submit an explicit owner report JSON file; retain its ID for exact replay."""
    try:
        submission = SubmitQuota.model_validate_json(_read(input_file, private=False, limit=4096))
        result = _request(base_url, token_file, "POST", "/v2/quota/observations", submission.model_dump(mode="json"))
        safe = _safe_view(result)
        if safe["observation"] != submission.observation.model_dump(mode="json"):
            raise ValueError("quota_response_mismatch")
        typer.echo(json.dumps(safe))
    except (ValueError, ValidationError, OSError, httpx.HTTPError):
        _failure()


@quota_app.command("show")
def show_quota(observation_id: str, token_file: Path = _TOKEN, base_url: str = _BASE) -> None:
    """Read one historical observation with current freshness; never refresh it."""
    from pydantic import TypeAdapter

    try:
        identifier = TypeAdapter(QuotaId).validate_python(observation_id)
        safe = _safe_view(_request(base_url, token_file, "GET", "/v2/quota/observations/" + identifier, None))
        if QuotaObservation.model_validate_json(json.dumps(safe["observation"])).observation_id != identifier:
            raise ValueError("quota_response_mismatch")
        typer.echo(json.dumps(safe))
    except (ValueError, ValidationError, OSError, httpx.HTTPError):
        _failure()


@quota_app.command("current")
def current_quota(
    account_ref: str = typer.Option(..., "--account-ref"),
    window_ref: str = typer.Option(..., "--window"),
    provider: str = typer.Option("claude-subscription", "--provider"),
    model_ref: str | None = typer.Option(None, "--model"),
    token_file: Path = _TOKEN,
    base_url: str = _BASE,
) -> None:
    """Read separate source lanes for one exact account/model/window scope."""
    try:
        query = QueryQuota(
            schema_version=1,
            scope=QuotaScope.model_validate(
                {
                    "provider": provider,
                    "account_ref": account_ref,
                    "window_ref": window_ref,
                    "model_ref": model_ref,
                }
            ),
        )
        result = _request(base_url, token_file, "POST", "/v2/quota/current", query.model_dump(mode="json"))
        if not isinstance(result, dict) or result.get("authority") != "OBSERVATION_ONLY":
            raise ValueError("invalid_quota_response")
        lanes = result.get("lanes")
        if not isinstance(lanes, list) or len(lanes) > 4:
            raise ValueError("invalid_quota_response")
        safe = [_safe_view(lane) for lane in lanes]
        bodies = [QuotaObservation.model_validate_json(json.dumps(lane["observation"])) for lane in safe]
        if any(body.scope != query.scope for body in bodies) or len({body.source for body in bodies}) != len(bodies):
            raise ValueError("quota_response_mismatch")
        typer.echo(json.dumps({"lanes": safe, "authority": "OBSERVATION_ONLY"}))
    except (ValueError, ValidationError, OSError, httpx.HTTPError):
        _failure()
