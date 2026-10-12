"""Request bounds. These checks do not start PostgreSQL."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from panestria.api.auth import MAX_BODY_BYTES, GoalApi
from panestria.api.main import create_app, mount_goal_api
from panestria.config import Settings

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
    assert body == {"code": "database_unavailable", "message": "database_unavailable", "retryable": True}
    encoded = json.dumps(body)
    assert "postgresql://" not in encoded
    assert "placeholder-not-a-secret" not in encoded
