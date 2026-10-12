"""Regressions for occupied API ports and a read-only local review listener."""

from __future__ import annotations

import hashlib
import http.client
import json
import socket
import subprocess
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

from panestria.demo import _running_api
from panestria.review import render_report, review_server

ROOT = Path(__file__).resolve().parents[2]
TOKEN = "synthetic-loopback-token"


@pytest.fixture(autouse=True)
def metadata(record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-001-TC02")
    record_property(
        "candidate_commit", subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    )
    record_property("lane", "contract")
    record_property("execution_mode", "OS_BOUNDARY")
    record_property("fixture_digest", hashlib.sha256(Path(__file__).read_bytes()).hexdigest())


@pytest.fixture
def listener() -> Iterator[tuple[str, list[tuple[str, str]]]]:
    observed: list[tuple[str, str]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            observed.append((self.path, self.headers.get("Authorization", "")))
            if self.path == "/healthz":
                self.send_response(200)
                body: object = {"schema_version": 1, "status": "live", "version": "0.0.0", "profile": "SYNTHETIC_DEV"}
            elif self.headers.get("Authorization") == f"Bearer {TOKEN}":
                self.send_response(200)
                body = {"approvals": []}
            else:
                self.send_response(401)
                body = {"code": "unauthorized"}
            payload = json.dumps(body).encode()
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            pass

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}", observed
        finally:
            server.shutdown()
            thread.join(timeout=5)


def test_existing_api_requires_health_and_bearer_identity(
    listener: tuple[str, list[tuple[str, str]]],
) -> None:
    base, observed = listener
    assert _running_api(base, TOKEN)
    assert observed == [("/healthz", ""), ("/v1/approvals", f"Bearer {TOKEN}")]
    with pytest.raises(SystemExit, match="cannot authenticate"):
        _running_api(base, "wrong-synthetic-token")
    assert _running_api(base, TOKEN), "the running API must not be stopped by a failed probe"


def test_closed_port_is_the_only_reason_to_start_an_api() -> None:
    with socket.socket() as held:
        held.bind(("127.0.0.1", 0))
        port = held.getsockname()[1]
        assert _running_api(f"http://127.0.0.1:{port}", TOKEN) is False
        held.listen()
        with pytest.raises(SystemExit, match="not a compatible Panestria API"):
            _running_api(f"http://127.0.0.1:{port}", TOKEN)


def _report() -> dict[str, Any]:
    return {
        "status": {"goal_id": "synthetic-goal", "status": "COMPLETED"},
        "artifact": {
            "artifact_id": "synthetic-artifact",
            "sha256": "a" * 64,
            "verdicts": [{"check_key": "independent-test", "verdict": "PASS"}],
        },
        "approvals": [{"label": "Merge", "receipt": {"state": "APPROVED"}}],
        "events": {"events": [{"seq": "1", "kind": "goal.completed", "payload": {"text": "<script>bad()</script>"}}]},
        "observed_at": "2026-10-12T00:00:00+00:00",
        "source_commit": "a" * 40,
        "base_url": "http://127.0.0.1:8765",
    }


def test_browser_snapshot_is_escaped_and_cannot_write_or_serve_files() -> None:
    page = render_report(_report())
    assert b"<script>bad()" not in page
    assert b"&lt;script&gt;" in page
    assert b"COMPLETED" in page and b"independent-test" in page
    with socket.socket() as held:
        held.bind(("127.0.0.1", 0))
        port = held.getsockname()[1]
    with review_server(page, port) as server:
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
            connection.request("GET", "/")
            response = connection.getresponse()
            assert response.status == 200 and response.read() == page
            assert response.getheader("Content-Security-Policy") is not None
            connection.request("POST", "/")
            response = connection.getresponse()
            assert response.status == 501
            response.read()
            connection.request("GET", "/../../.env")
            response = connection.getresponse()
            assert response.status == 404
            response.read()
            connection.request("GET", "/", headers={"Host": "other.example"})
            response = connection.getresponse()
            assert response.status == 403
            response.read()
            connection.request("GET", "/", headers={"Origin": "https://other.example"})
            response = connection.getresponse()
            assert response.status == 403
            response.read()
            connection.close()
        finally:
            server.shutdown()
            thread.join(timeout=5)


@pytest.mark.parametrize("port", [0, -1, 65536])
def test_review_port_validation(port: int) -> None:
    with pytest.raises(ValueError):
        review_server(b"synthetic", port)
