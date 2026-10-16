"""Owner-only HTTP observations with real PostgreSQL/session/CSRF scope."""

from uuid import uuid4

import psycopg
import pytest
from test_aos_009 import _client

from panestria.api.auth import GoalApi
from panestria.api.routes import quota as routes
from quota_support import observation

CLI = {"Authorization": "Bearer test-only-cli-token-at-least-16"}
ORIGIN = {"Origin": "http://127.0.0.1:8766"}


@pytest.fixture
def api(r1_task):
    client = _client(r1_task)
    value = observation()
    return (
        client,
        r1_task,
        {"schema_version": 1, "task_id": r1_task["task"], "observation": value.model_dump(mode="json")},
    )


def pair(client):
    code = client.post("/v1/session/code", json={}, headers=CLI).json()["code"]
    paired = client.post("/v1/session/pair", json={"code": code}, headers=ORIGIN)
    assert paired.status_code == 200
    return {**ORIGIN, "X-Panestria-CSRF": paired.json()["csrf_token"]}


def test_owner_40_percent_report_read_current_and_unknown_are_truthful(api):
    client, task, body = api
    created = client.post("/v2/quota/observations", json=body, headers=CLI)
    assert created.status_code == 201 and created.json()["effective_remaining"] == "40"
    assert created.json()["authority"] == "OBSERVATION_ONLY"
    assert created.headers["cache-control"] == "no-store"
    assert client.post("/v2/quota/observations", json=body, headers=CLI).status_code == 200
    url = "/v2/quota/observations/" + body["observation"]["observation_id"]
    assert client.get(url, headers=CLI).json()["observation"] == body["observation"]
    headers = pair(client)
    query = {"schema_version": 1, "scope": body["observation"]["scope"]}
    current = client.post("/v2/quota/current", json=query, headers=headers)
    assert current.status_code == 200 and len(current.json()["lanes"]) == 1
    unknown = {**body, "observation": observation(scope=query["scope"], remaining=None).model_dump(mode="json")}
    assert client.post("/v2/quota/observations", json=unknown, headers=headers).json()["confidence"] == "UNKNOWN"
    with psycopg.connect(task["dsn"]) as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.worker_invocation WHERE task_id=%s", (task["task"],)
        ).fetchone() == (0,)


@pytest.mark.parametrize(
    "changes",
    [
        {"source": "PROVIDER_REPORTED", "source_sha256": "ab" * 32},
        {"source": "ESTIMATED", "source_sha256": "ab" * 32},
        {"approved": True},
        {"owner_id": str(uuid4())},
        {"remaining": True},
        {"source_sha256": "ab" * 32},
        {"schema_version": True},
        {"fresh_for_seconds": 86401},
    ],
)
def test_http_cannot_impersonate_provider_estimator_authority_or_coerce_types(api, changes):
    client, task, body = api
    sent = {**body, "observation": {**body["observation"], **changes}}
    rejected = client.post("/v2/quota/observations", json=sent, headers=CLI)
    assert rejected.status_code == 422 and rejected.json()["code"] == "invalid_quota_request"
    assert "ab" * 32 not in rejected.text
    with psycopg.connect(task["dsn"]) as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.quota_observation WHERE task_id=%s", (task["task"],)
        ).fetchone() == (0,)


def test_bearer_session_host_origin_csrf_and_cap_are_enforced(api):
    client, _, body = api
    path = "/v2/quota/observations"
    assert client.post(path, json=body).status_code == 401
    assert client.post(path, json=body, headers={**CLI, "Host": "attacker.example"}).status_code == 403
    assert client.post(path, json=body, headers={**CLI, "Origin": "https://attacker.example"}).status_code == 403
    pair(client)
    assert client.post(path, json=body, headers=ORIGIN).status_code == 403
    assert (
        client.post(
            "/v2/quota/current", json={"schema_version": 1, "scope": body["observation"]["scope"]}, headers=ORIGIN
        ).status_code
        == 403
    )
    response = client.post(path, content=b"x" * 65537, headers={**CLI, "Content-Type": "application/json"})
    assert response.status_code == 413  # Body cap applies before transaction reauthorization.
    client.cookies.clear()
    response = client.post(path, content=b"x" * 65537, headers={**CLI, "Content-Type": "application/json"})
    assert response.status_code == 413 and response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("operation", ["submit", "read", "current"])
def test_actual_session_revoked_before_transaction_denies_every_path(api, monkeypatch, operation):
    client, task, body = api
    assert client.post("/v2/quota/observations", json=body, headers=CLI).status_code == 201
    headers = pair(client)
    original = routes._transaction

    def revoke(request, config, function):
        with psycopg.connect(task["dsn"]) as c:
            c.execute(
                "UPDATE panestria.browser_session SET revoked_at=clock_timestamp() WHERE project_id=%s",
                (task["project"],),
            )
        return original(request, config, function)

    monkeypatch.setattr(routes, "_transaction", revoke)
    if operation == "read":
        response = client.get("/v2/quota/observations/" + body["observation"]["observation_id"], headers=headers)
    elif operation == "current":
        response = client.post(
            "/v2/quota/current", json={"schema_version": 1, "scope": body["observation"]["scope"]}, headers=headers
        )
    else:
        response = client.post("/v2/quota/observations", json=body, headers=headers)
    assert response.status_code == 401 and response.json()["code"] == "unauthorized"
    assert response.headers["cache-control"] == "no-store"


def test_wrong_owner_project_malformed_body_path_and_duplicate_conflict_are_redacted(api):
    client, task, body = api
    assert client.post("/v2/quota/observations", json=body, headers=CLI).status_code == 201
    changed = {**body, "observation": {**body["observation"], "remaining": "41"}}
    assert client.post("/v2/quota/observations", json=changed, headers=CLI).status_code == 409
    sentinel = "SYNTHETIC_SECRET_NOT_A_QUOTA"
    assert sentinel not in client.post("/v2/quota/observations", content=sentinel, headers=CLI).text
    response = client.get("/v2/quota/observations/" + sentinel, headers=CLI)
    assert response.status_code == 422 and sentinel not in response.text
    for owner, project in ((str(uuid4()), task["project"]), (task["owner"], str(uuid4()))):
        client.app.state.goal_api = GoalApi(CLI["Authorization"][7:], owner, project, task["dsn"])
        assert (
            client.get("/v2/quota/observations/" + body["observation"]["observation_id"], headers=CLI).status_code
            == 404
        )
        current = client.post(
            "/v2/quota/current", json={"schema_version": 1, "scope": body["observation"]["scope"]}, headers=CLI
        )
        assert current.json()["lanes"] == []
        assert client.post("/v2/quota/observations", json=body, headers=CLI).status_code == 404


def test_health_only_app_does_not_mount_quota_routes():
    from fastapi.testclient import TestClient

    from panestria.api.main import create_app
    from panestria.config import Settings

    client = TestClient(
        create_app(
            Settings(
                database_url="postgresql://panestria_synthetic:placeholder-not-a-secret@127.0.0.1:55439/panestria_synthetic"
            ),
            lambda _: None,
        )
    )
    assert client.post("/v2/quota/observations", json={}, headers=CLI).status_code == 404
