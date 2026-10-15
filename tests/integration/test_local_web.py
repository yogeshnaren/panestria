"""Packaged browser surface and explicit pairing-code CLI over scoped HTTP."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from test_local_server import configured  # noqa: F401
from typer.testing import CliRunner

from panestria.cli import local
from panestria.cli.main import app as cli


def test_packaged_assets_preserve_csp_and_fixed_route_scope(configured):  # noqa: F811
    config, token, settings, app, calls = configured
    with TestClient(app, base_url=config.origin) as browser:
        page = browser.get("/")
        assert page.status_code == 200 and "A question, kept local." in page.text
        assert '<script src="/ui/ask.js" defer></script>' in page.text
        assert "unsafe-inline" not in page.headers["content-security-policy"]
        assert page.headers["cache-control"] == "no-store"
        assert token not in page.text and str(config.project_id) not in page.text
        script = browser.get("/ui/ask.js")
        assert script.status_code == 200 and "text/javascript" in script.headers["content-type"]
        assert browser.get("/ui/ask.css").status_code == 200
        assert browser.get("/ui/arbitrary-file").status_code == 404
        assert browser.get("/", headers={"Host": "attacker.invalid"}).status_code == 403
        assert not calls


def test_terminal_code_pairs_scoped_browser_without_exposing_bearer(configured, monkeypatch):  # noqa: F811
    config, token, settings, app, calls = configured
    with TestClient(app, base_url=config.origin) as browser:

        class TerminalClient:
            def __init__(self, **kwargs):
                assert kwargs == {"trust_env": False, "follow_redirects": False, "timeout": 5}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            @contextmanager
            def stream(self, method, url, **kwargs):
                # The terminal has no browser session cookies or Origin.
                terminal = TestClient(app, base_url=config.origin)
                try:
                    with terminal.stream(method, url, **kwargs) as response:
                        yield response
                finally:
                    terminal.close()

        monkeypatch.setattr(local.httpx, "Client", TerminalClient)
        path = config.token_file.parent / "local.json"
        issued = CliRunner().invoke(cli, ["local", "pair-code", "--config", str(path)])
        assert issued.exit_code == 0, issued.output
        body = json.loads(issued.output)
        assert body["origin"] == config.origin and body["expires_in_seconds"] == 120
        assert token not in issued.output
        origin = {"Origin": config.origin}
        paired = browser.post("/v1/session/pair", json={"code": body["code"]}, headers=origin)
        assert paired.status_code == 200
        assert "HttpOnly" in paired.headers.get("set-cookie", "")
        request = {
            "request_id": str(uuid4()),
            "project_id": str(config.project_id),
            "question": "Say READY",
            "privacy_label": "RESTRICTED",
            "offline": True,
            "retain_response": False,
        }
        assert browser.post("/v1/ask", json=request, headers=origin).status_code == 403
        headers = {**origin, "X-Panestria-CSRF": paired.json()["csrf_token"]}
        assert browser.get("/v1/local/status").json()["project_id"] == str(config.project_id)
        reply = browser.post("/v1/ask", json=request, headers=headers)
        assert reply.status_code == 200 and reply.json()["text"] == "READY"
        assert browser.post("/v1/session/logout", json={}, headers=headers).status_code == 200
        assert browser.get("/v1/local/status").status_code == 401


@pytest.mark.parametrize(
    "status,body",
    [(401, {"code": "SYNTHETIC_PRIVATE"}), (200, {"code": "invalid"}), (200, []), (200, {"code": "A" * 5000})],
)
def test_pairing_cli_rejects_bounded_malformed_or_unauthorized_responses(configured, monkeypatch, status, body):  # noqa: F811
    config, token, settings, app, calls = configured
    original = httpx.Client

    def create(**kwargs):
        return original(**kwargs, transport=httpx.MockTransport(lambda request: httpx.Response(status, json=body)))

    monkeypatch.setattr(local.httpx, "Client", create)
    result = CliRunner().invoke(cli, ["local", "pair-code", "--config", str(config.token_file.parent / "local.json")])
    assert result.exit_code == 2 and json.loads(result.output) == {"code": "local_pairing_unavailable"}
    assert token not in result.output and "SYNTHETIC_PRIVATE" not in result.output
    app.state.health.shutdown()


def test_browser_storage_and_rendering_contract():
    script = Path(__file__).resolve().parents[2] / "src/panestria/api/assets/ask.js"
    source = script.read_text()
    # Enforce the narrow persistence/rendering boundary in addition to actual
    # browser behavior qualification. No permissive dynamic HTML sink is needed.
    for forbidden in (
        "innerHTML",
        "outerHTML",
        "insertAdjacentHTML",
        "localStorage",
        "sessionStorage",
        "indexedDB",
        "console.",
        "serviceWorker",
        "eval(",
    ):
        assert forbidden not in source
    assert 'credentials: "same-origin"' in source and 'redirect: "error"' in source
    assert 'window.addEventListener("pagehide"' in source
