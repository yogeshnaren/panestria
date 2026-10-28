"""The API publishes no schema route and never describes rejected input before authentication."""

import asyncio

from fastapi.testclient import TestClient

from panestria.api import serve
from panestria.api.auth import GoalApi
from panestria.api.main import create_app, mount_goal_api
from panestria.config import Settings

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


class _Writer:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data

    async def drain(self):
        pass

    def close(self):
        pass

    async def wait_closed(self):
        pass

    def get_extra_info(self, name):
        return ("127.0.0.1", 1)


def _handle(raw: bytes, *, eof: bool) -> bytes:
    async def once():
        reader = asyncio.StreamReader()
        reader.feed_data(raw)
        if eof:
            reader.feed_eof()
        writer = _Writer()
        await serve._handle(_app(), ("127.0.0.1", 0), reader, writer)
        return writer.data

    return asyncio.run(once())


def test_stalled_request_is_answered_with_a_deadline_error(monkeypatch):
    monkeypatch.setattr(serve, "REQUEST_DEADLINE_SECONDS", 0.05)
    response = _handle(b"GET /healthz HTTP/1.1\r\nHost: 127.0.0.1\r\n", eof=False)
    assert response.startswith(b"HTTP/1.1 408 Request Timeout") and b"request_deadline_exceeded" in response


def test_truncated_body_closes_without_a_response():
    response = _handle(b"POST /v1/goals HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 10\r\n\r\nshort", eof=True)
    assert response == b""
