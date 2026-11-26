"""The API publishes no schema route and never describes rejected input before authentication."""

from fastapi.testclient import TestClient

from panestria.api.auth import GoalApi
from panestria.api.local_protocol import LocalHttpProtocol
from panestria.api.main import create_app, mount_goal_api
from panestria.api.serving import GOAL_API_PROTOCOL, TransportLimits
from panestria.config import Settings
from serving_support import exchange, served

TOKEN = "synthetic-loopback-token"
OWNER = "00000000-0000-4000-8000-000000000002"
PROJECT = "00000000-0000-4000-8000-000000000003"
CLOSED = "postgresql://panestria_synthetic:placeholder-not-a-secret@127.0.0.1:1/panestria_synthetic"


def _app():
    settings = Settings(
        schema_version=1,
        profile="SYNTHETIC_DEV",
        bind_host="127.0.0.1",
        bind_port=8765,
        readiness_budget_ms=200,
        database_url=CLOSED,  # type: ignore[arg-type]
    )
    application = create_app(settings, lambda _deadline: None)  # type: ignore[arg-type, return-value]
    mount_goal_api(application, GoalApi(TOKEN, OWNER, PROJECT, CLOSED))
    return application


def test_schema_is_generated_offline_but_not_served():
    application = _app()
    with TestClient(application, base_url="http://127.0.0.1") as client:
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/docs").status_code == 404
    assert "/healthz" in application.openapi()["paths"]


def test_invalid_typed_input_is_unauthorized_before_it_is_described():
    with TestClient(_app(), base_url="http://127.0.0.1") as client:
        anonymous = client.get("/v1/approvals", params={"limit": "not-a-number"})
        assert anonymous.status_code == 401 and anonymous.json()["code"] == "unauthorized"
        foreign = client.get("/v1/approvals", params={"limit": "x"}, headers={"host": "evil.example"})
        assert foreign.status_code == 403 and foreign.json()["code"] == "invalid_host"
        invalid = client.get(
            "/v1/approvals", params={"limit": "not-a-number"}, headers={"authorization": f"Bearer {TOKEN}"}
        )
    assert invalid.status_code == 422 and invalid.json()["code"] == "invalid_request"
    assert "detail" not in invalid.json() and "limit" not in invalid.text


def _served_app(deadline_seconds: float = 10.0):  # type: ignore[no-untyped-def]
    application = _app()
    application.add_middleware(TransportLimits, deadline_seconds=deadline_seconds)
    return application


def test_stalled_headers_are_answered_with_a_deadline_error(monkeypatch):
    monkeypatch.setattr(LocalHttpProtocol, "header_deadline_seconds", 0.2)
    with served(_served_app(), http=GOAL_API_PROTOCOL) as port:
        response = exchange(port, b"GET /healthz HTTP/1.1\r\nHost: 127.0.0.1\r\n", timeout=3)
    assert response.startswith(b"HTTP/1.1 408 Request Timeout") and b"request_deadline_exceeded" in response


def test_an_idle_connection_is_closed_without_a_reply(monkeypatch):
    monkeypatch.setattr(LocalHttpProtocol, "header_deadline_seconds", 0.2)
    with served(_served_app(), http=GOAL_API_PROTOCOL) as port:
        assert exchange(port, b"", timeout=3) == b""


def test_other_servers_close_stalled_headers_without_a_reply(monkeypatch):
    # The Ask and Mission Control servers keep their silent close (test_local_server).
    monkeypatch.setattr(LocalHttpProtocol, "header_deadline_seconds", 0.2)
    with served(_served_app()) as port:
        assert exchange(port, b"GET /healthz HTTP/1.1\r\nHost: 127.0.0.1\r\n", timeout=3) == b""


def test_a_stalled_body_is_answered_with_a_deadline_error():
    with served(_served_app(deadline_seconds=0.2)) as port:
        response = exchange(
            port,
            b"POST /v1/goals HTTP/1.1\r\nHost: 127.0.0.1\r\nAuthorization: Bearer "
            + TOKEN.encode()
            + b'\r\nIdempotency-Key: stalled\r\nContent-Type: application/json\r\nContent-Length: 10\r\n\r\n{"a"',
            timeout=3,
        )
    assert response.startswith(b"HTTP/1.1 408 ") and b"request_deadline_exceeded" in response


def test_truncated_body_closes_without_a_response():
    truncated = b"Content-Type: application/json\r\nContent-Length: 10\r\n\r\nshort"
    with served(_served_app()) as port:
        authenticated = exchange(
            port,
            b"POST /v1/goals HTTP/1.1\r\nHost: 127.0.0.1\r\nAuthorization: Bearer "
            + TOKEN.encode()
            + b"\r\nIdempotency-Key: truncated\r\n"
            + truncated,
            shutdown_write=True,
        )
        anonymous = exchange(port, b"POST /v1/goals HTTP/1.1\r\nHost: 127.0.0.1\r\n" + truncated, shutdown_write=True)
    # A body that never completes is not processed and gets no reply.
    assert authenticated == b""
    # Authentication is checked before the body is read, so an anonymous one is refused first.
    assert anonymous.startswith(b"HTTP/1.1 401 ") and b"unauthorized" in anonymous
