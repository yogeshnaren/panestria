"""Bounded CLI input, private token-file handling and explicit offline requests."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import httpx2 as httpx
import pytest
from typer.testing import CliRunner

from panestria.cli.main import app


def test_ask_cli_offline_and_private_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    token = tmp_path / "token"
    token.write_text("synthetic-loopback-token-not-an-api-key")
    token.chmod(0o600)
    project = str(uuid4())
    calls = []

    def send(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body = json.loads(request.content)
        assert body["offline"] is True and body["retain_response"] is False and body["project_id"] == project
        assert body["question"] == "Say READY"
        return httpx.Response(
            200, json={"request_id": body["request_id"], "state": "COMPLETED", "text": "READY", "sources": []}
        )

    client = httpx.Client

    def configured(**kwargs: object) -> httpx.Client:
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        return client(transport=httpx.MockTransport(send), **kwargs)

    monkeypatch.setattr(httpx, "Client", configured)
    runner = CliRunner()
    args = ["ask", "Say READY", "--project", project, "--token-file", str(token)]
    result = runner.invoke(app, args)
    assert result.exit_code == 0 and "READY" in result.output and token.read_text() not in result.output
    assert len(calls) == 1
    rejected = runner.invoke(app, [*args, "--base-url", "https://remote.example"])
    assert rejected.exit_code == 2 and len(calls) == 1
    token.chmod(0o644)
    assert runner.invoke(app, args).exit_code == 2 and len(calls) == 1
