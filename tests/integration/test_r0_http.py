"""Request bounds, over a real socket under the product server. These checks do not start PostgreSQL."""

from __future__ import annotations

import json
import socket
import threading
import time
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from panestria.api.auth import MAX_BODY_BYTES, MAX_HEADER_LINE_BYTES, GoalApi
from panestria.api.db import DatabaseUnavailable
from panestria.api.main import create_app, mount_goal_api
from panestria.api.serving import TransportLimits
from panestria.config import Settings
from serving_support import exchange, served

TOKEN = "synthetic-loopback-token"
OWNER = "00000000-0000-4000-8000-000000000002"
PROJECT = "00000000-0000-4000-8000-000000000003"
CLOSED = "postgresql://panestria_synthetic:placeholder-not-a-secret@127.0.0.1:1/panestria_synthetic"


def _client(database_url: str) -> TestClient:
    settings = Settings(
        schema_version=1,
        profile="SYNTHETIC_DEV",
        bind_host="127.0.0.1",
        bind_port=8765,
        readiness_budget_ms=200,
        database_url=database_url,  # type: ignore[arg-type]
    )
    application = create_app(settings, lambda _deadline: None)  # type: ignore[arg-type, return-value]
    mount_goal_api(application, GoalApi(TOKEN, OWNER, PROJECT, database_url))
    return TestClient(application, base_url="http://127.0.0.1")


def _roundtrip(port: int, payload: bytes) -> bytes:
    with socket.create_connection(("127.0.0.1", port), timeout=2) as sock:
        sock.sendall(payload)
        chunks: list[bytes] = []
        while True:
            data = sock.recv(4096)
            if not data:
                break
            chunks.append(data)
    return b"".join(chunks)


def _r0_app(database_url: str):  # type: ignore[no-untyped-def]
    """The goal API exactly as ``python -m panestria.api.serve`` assembles it."""
    application = create_app(
        Settings(
            schema_version=1,
            profile="SYNTHETIC_DEV",
            bind_host="127.0.0.1",
            bind_port=8765,
            readiness_budget_ms=200,
            database_url=database_url,  # type: ignore[arg-type]
        ),
        lambda _deadline: None,  # type: ignore[arg-type, return-value]
    )
    mount_goal_api(application, GoalApi(TOKEN, OWNER, PROJECT, database_url))
    application.add_middleware(TransportLimits)
    return application


def _health_during_submit(entered: threading.Event) -> tuple[float, bytes, bytes]:
    with served(_r0_app(CLOSED)) as port:
        return _exchange(port, entered)


def _exchange(port: int, entered: threading.Event) -> tuple[float, bytes, bytes]:
    post = (
        b"POST /v1/goals HTTP/1.1\r\nHost: 127.0.0.1\r\n"
        b"Authorization: Bearer " + TOKEN.encode() + b"\r\n"
        b"Idempotency-Key: slow-db\r\nContent-Type: application/json\r\n"
        b"Content-Length: 2\r\nConnection: close\r\n\r\n{}"
    )
    health = b"GET /healthz HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n"
    posted: list[bytes] = []

    def send_post() -> None:
        posted.append(_roundtrip(port, post))

    worker = threading.Thread(target=send_post)
    worker.start()
    assert entered.wait(2)
    started = time.monotonic()
    health_body = _roundtrip(port, health)
    elapsed = time.monotonic() - started
    worker.join(2)
    assert posted
    return elapsed, health_body, posted[0]


def test_oversized_header_is_rejected_without_echo(record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-001-TC01")
    marker = b"A" * (MAX_HEADER_LINE_BYTES + 1)
    host = b"Host: 127.0.0.1\r\nConnection: close\r\n"
    with served(_r0_app(CLOSED)) as port:
        oversized = exchange(port, b"GET /" + marker + b" HTTP/1.1\r\n" + host + b"\r\n")
        header = exchange(port, b"GET /healthz HTTP/1.1\r\n" + host + b"X-Pad: " + marker + b"\r\n\r\n")
        negative = exchange(port, b"POST /v1/goals HTTP/1.1\r\n" + host + b"Content-Length: -1\r\n\r\n")
        chunked = exchange(port, b"POST /v1/goals HTTP/1.1\r\n" + host + b"Transfer-Encoding: chunked\r\n\r\n0\r\n\r\n")
        repeated = exchange(
            port, b"POST /v1/goals HTTP/1.1\r\n" + host + b"Content-Length: 1\r\nContent-Length: 2\r\n\r\nx"
        )
        declared = exchange(
            port, b"POST /v1/goals HTTP/1.1\r\n" + host + b"Content-Length: %d\r\n\r\n" % (MAX_BODY_BYTES + 1)
        )
        healthy = exchange(port, b"GET /healthz HTTP/1.1\r\n" + host + b"\r\n")
    for refused in (oversized, header, negative, chunked, repeated):
        assert refused.startswith(b"HTTP/1.1 400 "), refused[:80]
        assert b"invalid_request" in refused and b"application/json" in refused
        assert marker not in refused
    # Refused from the declared length alone, before any body byte is sent.
    assert declared.startswith(b"HTTP/1.1 413 ") and b"body_too_large" in declared
    assert healthy.startswith(b"HTTP/1.1 200 ")


def test_submit_stops_reading_past_the_body_cap(record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-001-TC01")
    with _client(CLOSED) as client:
        response = client.post(
            "/v1/goals",
            content=b"{" + b"x" * (MAX_BODY_BYTES + 1),
            headers={"Authorization": f"Bearer {TOKEN}", "Idempotency-Key": "too-large"},
        )
    assert response.status_code == 413
    assert response.json()["code"] == "body_too_large"


def test_slow_database_call_leaves_health_responsive(
    monkeypatch: pytest.MonkeyPatch, record_property: pytest.RecordProperty
) -> None:
    record_property("gate_case_id", "AOS-001-TC01")
    entered = threading.Event()

    def blocked(url: str) -> None:
        del url
        entered.set()
        time.sleep(0.6)
        raise DatabaseUnavailable

    monkeypatch.setattr("panestria.api.routes.goals.open_database", blocked)
    elapsed, health, denied = _health_during_submit(entered)
    assert elapsed < 0.3
    assert health.startswith(b"HTTP/1.1 200 ")
    assert b"database_unavailable" in denied
    assert b"postgresql://" not in denied


def test_database_outage_is_unavailable(record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-001-TC01")
    with _client(CLOSED) as client:
        response = client.post(
            "/v1/goals",
            content=b'{"schema_version":1}',
            headers={"Authorization": f"Bearer {TOKEN}", "Idempotency-Key": "closed-port"},
        )
    assert response.status_code == 503
    body = response.json()
    assert set(body) == {"code", "correlation_id", "message", "retryable"}
    assert body["code"] == "database_unavailable"
    assert body["message"] == "database_unavailable"
    assert body["retryable"] is True
    assert UUID(str(body["correlation_id"])).version == 4
    encoded = json.dumps(body)
    assert "postgresql://" not in encoded
    assert "placeholder-not-a-secret" not in encoded


def test_denial_correlation_id_is_not_taken_from_the_request(record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-005-TC02")
    forged = "11111111-1111-4111-8111-111111111111"
    with _client(CLOSED) as client:
        headers = {
            "Authorization": "Bearer not-the-token",
            "Idempotency-Key": "forged",
            "X-Correlation-Id": forged,
        }
        first = client.post("/v1/goals", content=b"{}", headers=headers)
        second = client.post("/v1/goals", content=b"{}", headers=headers)
    assert first.status_code == 401
    assert second.status_code == 401
    one = first.json()
    two = second.json()
    assert one["code"] == "unauthorized"
    assert one["retryable"] is False
    assert one["correlation_id"] != forged
    assert two["correlation_id"] != forged
    assert one["correlation_id"] != two["correlation_id"]
    assert UUID(str(one["correlation_id"])).version == 4
    assert "postgresql://" not in json.dumps(one)
