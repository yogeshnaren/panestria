"""Explicit local Ask client; token files keep credentials out of command arguments."""

from __future__ import annotations

import ipaddress
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx2 as httpx
import typer
from pydantic import ValidationError

from panestria.contracts.ask import AskSubmission

_TOKEN_FILE = typer.Option(..., "--token-file", exists=True, dir_okay=False)
_QUESTION_FILE = typer.Option(None, "--question-file", exists=True, dir_okay=False)


def ask_command(
    question: str | None = typer.Argument(None),
    project: str = typer.Option(..., "--project"),
    base_url: str = typer.Option("http://127.0.0.1:8766", "--base-url"),
    token_file: Path = _TOKEN_FILE,
    question_file: Path | None = _QUESTION_FILE,
    privacy: str = typer.Option("PRIVATE", "--privacy"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Ask offline; provide a question argument, a file or bounded standard input."""
    try:
        parts = urlsplit(base_url)
        if (
            parts.scheme != "http"
            or parts.hostname is None
            or parts.port is None
            or parts.path
            or parts.query
            or parts.fragment
            or parts.username
        ):
            raise ValueError("invalid_loopback_url")
        if parts.hostname != "localhost" and not ipaddress.ip_address(parts.hostname).is_loopback:
            raise ValueError("invalid_loopback_url")
        stat = token_file.stat()
        if (
            token_file.is_symlink()
            or stat.st_uid != os.getuid()
            or stat.st_mode & 0o077
            or not 16 <= stat.st_size <= 256
        ):
            raise ValueError("token_file_must_be_private")
        token = token_file.read_text().strip()
        if question is not None and question_file is not None:
            raise ValueError("choose_one_question_source")
        if question_file is not None:
            with question_file.open("rb") as stream:
                question = stream.read(4097).decode()
        elif question is None:
            question = sys.stdin.buffer.read(4097).decode()
        submission = AskSubmission.model_validate(
            {
                "request_id": str(uuid4()),
                "project_id": project,
                "question": question,
                "privacy_label": privacy,
            }
        )
        with httpx.Client(trust_env=False, follow_redirects=False, timeout=65) as client:
            with client.stream(
                "POST", f"{base_url}/v1/ask", json=submission.model_dump(), headers={"Authorization": f"Bearer {token}"}
            ) as response:
                chunks, total = [], 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > 1024 * 1024:
                        raise ValueError("api_response_limit")
                    chunks.append(chunk)
                status, body = response.status_code, json.loads(b"".join(chunks))
        if status != 200:
            code = body.get("code", "ask_unavailable")
            if (
                not isinstance(code, str)
                or len(code) > 80
                or not all(c.islower() or c.isdigit() or c == "_" for c in code)
            ):
                code = "ask_unavailable"
            typer.echo(code, err=True)
            raise typer.Exit(1)
        if json_output:
            typer.echo(json.dumps(body))
        else:
            typer.echo(body.get("text", "Response not retained; receipt available."))
            typer.echo(f"Request: {body.get('request_id')} | {body.get('state')} | offline")
            for source in body.get("sources", []):
                typer.echo(f"Context source: {source['source_id']} (revision {source['revision_id']})")
    except (ValueError, ValidationError, OSError, httpx.HTTPError):
        typer.echo("ask_input_or_api_unavailable", err=True)
        raise typer.Exit(2) from None
