"""Owner HTTP/CSRF admission with actual ciphertext persistence; no providers."""

from __future__ import annotations

from uuid import uuid4

import psycopg
import pytest
from test_aos_009 import _client
from test_profile_vault import profile  # noqa: F401

from panestria.api.main import mount_profile_api
from panestria.api.routes import profiles
from panestria.api.routes.profiles import ProfileApi

CLI = {"Authorization": "Bearer test-only-cli-token-at-least-16"}
ORIGIN = {"Origin": "http://127.0.0.1:8766"}
SENTINEL = "SYNTHETIC_EXPLICIT_OWNER_PROFILE_世界"


@pytest.fixture
def api(profile, r1_task):  # noqa: F811
    dsn, actor, handle, keys, vault = profile
    client = _client(r1_task)
    mount_profile_api(client.app, ProfileApi(vault))
    payload = {
        "schema_version": 1,
        "profile_id": handle.profile_id,
        "key_id": handle.key_id,
        "intent": "SAVE_RESTRICTED_PROFILE",
        "document": {"schema_version": 1, "fields": {"background": SENTINEL}, "approved_for_local_context": []},
    }
    return client, dsn, actor, handle, keys, vault, payload


def pair(client):
    code = client.post("/v1/session/code", json={}, headers=CLI).json()["code"]
    result = client.post("/v1/session/pair", json={"code": code}, headers=ORIGIN)
    assert result.status_code == 200
    return {**ORIGIN, "X-Panestria-CSRF": result.json()["csrf_token"]}


def test_explicit_owner_http_profile_lifecycle(api, caplog):
    client, dsn, actor, handle, keys, vault, payload = api
    response = client.post("/v2/profiles", json=payload, headers=CLI)
    assert response.status_code == 201 and SENTINEL not in response.text
    created = response.json()
    assert created["classification"] == "RESTRICTED" and created["row_version"] == 0
    headers = pair(client)
    url = f"/v2/profiles/{handle.profile_id}"
    viewed = client.post(
        url + "/view", json={"schema_version": 1, "expected_version": 0, "purpose": "OWNER_REVIEW"}, headers=headers
    )
    assert viewed.status_code == 200 and viewed.json()["document"]["fields"]["background"] == SENTINEL
    assert viewed.headers["cache-control"] == "no-store" and viewed.headers["referrer-policy"] == "no-referrer"
    correction = {
        "schema_version": 1,
        "expected_version": 0,
        "key_id": handle.key_id,
        "intent": payload["intent"],
        "document": {"fields": {"background": "CORRECTED_SYNTHETIC_STATEMENT"}},
    }
    changed = client.post(url + "/correct", json=correction, headers=headers)
    assert changed.status_code == 201 and changed.json()["row_version"] == 1
    keys.loads.clear()
    stale = client.post(
        url + "/view", json={"schema_version": 1, "expected_version": 0, "purpose": "OWNER_REVIEW"}, headers=headers
    )
    assert stale.status_code == 409 and stale.json()["code"] == "version_conflict" and not keys.loads
    keys.values.clear()
    suppressed = client.post(url + "/suppress", json={"schema_version": 1, "expected_version": 1}, headers=headers)
    assert suppressed.status_code == 200 and suppressed.json()["row_version"] == 2
    hidden = client.post(
        url + "/view", json={"schema_version": 1, "expected_version": 2, "purpose": "OWNER_REVIEW"}, headers=headers
    )
    assert hidden.json()["code"] == "profile_suppressed" and SENTINEL not in hidden.text
    with psycopg.connect(dsn) as c:
        rows = c.execute(
            "SELECT consented_by::text,consent_ref::text FROM panestria.profile_revision WHERE profile_id=%s",
            (handle.profile_id,),
        ).fetchall()
        assert len(rows) == 2 and len({row[1] for row in rows}) == 2 and all(row[0] == actor.owner_id for row in rows)
        assert c.execute(
            "SELECT count(*) FROM panestria.memory_source WHERE project_id=%s", (actor.project_id,)
        ).fetchone() == (0,)
    assert SENTINEL not in caplog.text


@pytest.mark.parametrize(
    "extra", ["owner_id", "project_id", "approved", "consented_by", "consent_ref", "key", "key_store"]
)
def test_client_cannot_supply_authority_or_key_material(api, extra):
    client, dsn, actor, handle, keys, vault, payload = api
    keys.loads.clear()
    response = client.post("/v2/profiles", json={**payload, extra: SENTINEL}, headers=CLI)
    assert response.status_code == 422 and response.json()["code"] == "invalid_profile_request"
    assert SENTINEL not in response.text and not keys.loads


@pytest.mark.parametrize("version", [True, 1.0, "1", 2])
def test_api_version_is_exact(api, version):
    client, dsn, actor, handle, keys, vault, payload = api
    response = client.post("/v2/profiles", json={**payload, "schema_version": version}, headers=CLI)
    assert response.status_code == 422 and SENTINEL not in response.text


def test_auth_origin_host_csrf_and_disabled_defaults(api):
    client, dsn, actor, handle, keys, vault, payload = api
    keys.loads.clear()
    assert client.post("/v2/profiles", json=payload).status_code == 401
    assert client.post("/v2/profiles", json=payload, headers={**CLI, "Host": "attacker.example"}).status_code == 403
    assert (
        client.post("/v2/profiles", json=payload, headers={**CLI, "Origin": "https://evil.example"}).status_code == 403
    )
    headers = pair(client)
    assert client.post("/v2/profiles", json=payload, headers=ORIGIN).status_code == 403
    vault.enabled = False
    denied = client.post("/v2/profiles", json=payload, headers=headers)
    assert denied.status_code == 503 and denied.json()["code"] == "profile_disabled" and not keys.loads
    assert denied.headers["cache-control"] == "no-store"
    assert client.get(f"/v2/profiles/{handle.profile_id}/view", headers=CLI).status_code == 405


def test_missing_keys_oversized_documents_and_duplicate_create(api):
    client, dsn, actor, handle, keys, vault, payload = api
    missing = {**payload, "key_id": str(uuid4())}
    denied = client.post("/v2/profiles", json=missing, headers=CLI)
    assert denied.status_code == 409 and denied.json()["code"] == "key_handle_missing"
    oversized = {**payload, "document": {"fields": {"background": SENTINEL * 1000}}}
    invalid = client.post("/v2/profiles", json=oversized, headers=CLI)
    assert invalid.status_code == 422 and SENTINEL not in invalid.text
    oversized["document"]["fields"]["background"] = SENTINEL * 3000
    assert client.post("/v2/profiles", json=oversized, headers=CLI).status_code == 413
    assert client.post("/v2/profiles", json=payload, headers=CLI).status_code == 201
    keys.loads.clear()
    duplicate = client.post("/v2/profiles", json=payload, headers=CLI)
    assert duplicate.status_code == 409 and not keys.loads


@pytest.mark.parametrize("operation", ["create", "view"])
def test_session_revoked_between_authorization_and_transaction_denies_before_key(api, monkeypatch, operation):
    client, dsn, actor, handle, keys, vault, payload = api
    if operation == "view":
        assert client.post("/v2/profiles", json=payload, headers=CLI).status_code == 201
    headers = pair(client)
    original = profiles._transaction

    def revoke(request, config, function):
        with psycopg.connect(dsn) as c:
            c.execute(
                "UPDATE panestria.browser_session SET revoked_at=clock_timestamp() WHERE owner_id=%s AND project_id=%s",
                (actor.owner_id, actor.project_id),
            )
        return original(request, config, function)

    monkeypatch.setattr(profiles, "_transaction", revoke)
    keys.loads.clear()
    path = "/v2/profiles" if operation == "create" else f"/v2/profiles/{handle.profile_id}/view"
    body = payload if operation == "create" else {"schema_version": 1, "expected_version": 0, "purpose": "OWNER_REVIEW"}
    response = client.post(path, json=body, headers=headers)
    assert response.status_code == 401 and response.json()["code"] == "unauthorized"
    assert SENTINEL not in response.text and not keys.loads


def test_wrong_project_and_invalid_path_are_redacted(api, r1_task):
    client, dsn, actor, handle, keys, vault, payload = api
    assert client.post("/v2/profiles", json=payload, headers=CLI).status_code == 201
    body = {"schema_version": 1, "expected_version": 0, "purpose": "OWNER_REVIEW"}
    invalid = client.post(f"/v2/profiles/{SENTINEL}/view", json=body, headers=CLI)
    assert invalid.status_code == 422 and SENTINEL not in invalid.text
    from panestria.api.auth import GoalApi

    client.app.state.goal_api = GoalApi("test-only-cli-token-at-least-16", actor.owner_id, str(uuid4()), dsn)
    keys.loads.clear()
    denied = client.post(f"/v2/profiles/{handle.profile_id}/view", json=body, headers=CLI)
    assert denied.status_code == 404 and not keys.loads
