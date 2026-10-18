"""Actual owner HTTP/PG reviews; declarations never connect or dispatch."""

import copy
import json
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from test_aos_009 import _client
from test_quota_api import pair

from connection_support import manifest, proposal
from panestria.api.auth import GoalApi
from panestria.api.db import DatabaseUnavailable
from panestria.api.routes import connections as routes
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.policy import PolicyService
from panestria.kernel.repositories.policy import active_policy_ref
from panestria.kernel.uow import UnitOfWork
from panestria.policy.profiles import CertificateStore

CLI = {"Authorization": "Bearer test-only-cli-token-at-least-16"}
BASE = "/v2/connections"


@pytest.fixture
def configured(r1_task, tmp_path):
    actor = Actor(r1_task["owner"], r1_task["project"])
    with psycopg.connect(r1_task["dsn"]) as c:
        PolicyService(CertificateStore(tmp_path, {})).initialize(UnitOfWork(c), actor, r1_task["task"])
    with psycopg.connect(r1_task["dsn"]) as c:
        policy = active_policy_ref(UnitOfWork(c), actor.owner_id, actor.project_id)
    return (
        _client(r1_task),
        r1_task,
        {
            "schema_version": 1,
            "task_id": r1_task["task"],
            "change": proposal(policy, manifest(actor.owner_id, actor.project_id)).model_dump(mode="json"),
        },
    )


def submit(client, body):
    result = client.post(BASE + "/reviews", json=body, headers=CLI)
    assert result.status_code == 201
    return result.json()


def decide(client, view, decision="approve", headers=None):
    return client.post(
        BASE + "/reviews/" + view["proposal_id"] + "/decision",
        headers=headers or CLI,
        json={"schema_version": 1, "effect_digest": view["effect_digest"], "decision": decision},
    )


def test_exact_owner_review_approval_replay_and_read_are_never_runtime_authority(configured, monkeypatch):
    from panestria.kernel.connection_roots import ConnectionRootSession

    def forbidden(*args, **kwargs):
        raise AssertionError("HTTP declaration must not enroll a root")

    monkeypatch.setattr(ConnectionRootSession, "enroll", forbidden)
    client, task, body = configured
    with psycopg.connect(task["dsn"]) as c:
        before = c.execute(
            "SELECT state,row_version,lease_epoch FROM panestria.task WHERE id=%s", (task["task"],)
        ).fetchone()
    view = submit(client, body)
    assert view["manifest"] == body["change"]["manifest"]
    assert view["state"] == "PENDING" and not view["runtime_available"]
    assert client.get(BASE + "/reviews/" + view["proposal_id"], headers=CLI).json() == view
    receipt = decide(client, view)
    assert receipt.status_code == 200 and receipt.json()["granted_version"] == 1
    current = client.get(BASE + "/grants/" + view["grant_id"], headers=CLI)
    assert current.status_code == 200 and current.json()["state"] == "DECLARED_ACTIVE"
    assert current.json()["policy_status"] == "CURRENT" and current.json()["manifest"] == view["manifest"]
    for response in (receipt, current):
        assert response.json()["authority"] == "DECLARATION_ONLY"
        assert response.json()["conformance_status"] == "UNVERIFIED" and response.json()["runtime_available"] is False
        assert response.headers["cache-control"] == "no-store"
    replay = client.post(BASE + "/reviews", json=body, headers=CLI)
    assert replay.status_code == 200 and replay.json()["state"] == "APPROVED" and replay.json()["replayed"]
    assert decide(client, view).json()["replayed"]
    assert decide(client, view, "deny").status_code == 409
    with psycopg.connect(task["dsn"]) as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.worker_invocation WHERE task_id=%s", (task["task"],)
        ).fetchone() == (0,)
        assert (
            c.execute(
                "SELECT state,row_version,lease_epoch FROM panestria.task WHERE id=%s", (task["task"],)
            ).fetchone()
            == before
        )
        events = c.execute(
            "SELECT payload FROM panestria.task_event WHERE task_id=%s AND kind LIKE 'connection.%%'", (task["task"],)
        ).fetchall()
        assert "example.com" not in json.dumps(events) and len(events) == 2


def test_revoke_and_historical_receipt_cannot_reactivate_declaration(configured):
    client, _, body = configured
    first = submit(client, body)
    assert decide(client, first).status_code == 200
    body["change"] = proposal(
        body["change"]["policy_ref"],
        None,
        proposal_id=str(uuid4()),
        grant_id=first["grant_id"],
        expected_version=1,
        operation="REVOKE",
    ).model_dump(mode="json")
    revoked = submit(client, body)
    assert revoked["manifest"] == first["manifest"] and decide(client, revoked).status_code == 200
    old = decide(client, first).json()
    assert old["replayed"] and old["granted_version"] == 1 and old["runtime_available"] is False
    current = client.get(BASE + "/grants/" + first["grant_id"], headers=CLI).json()
    assert current["state"] == "DECLARED_REVOKED" and current["version"] == 2


def test_deny_and_changed_retry_do_not_create_active_revision(configured):
    client, _, body = configured
    view = submit(client, body)
    assert decide(client, view, "deny").json()["decision"] == "DENIED"
    assert decide(client, view, "deny").json()["replayed"]
    body["change"]["manifest"]["budget"]["max_calls"] = 1
    assert client.post(BASE + "/reviews", json=body, headers=CLI).status_code == 409
    current = client.get(BASE + "/grants/" + view["grant_id"], headers=CLI)
    assert current.status_code == 422 and current.json()["code"] == "connection_not_declared"


@pytest.mark.parametrize(
    "defect",
    [
        "version-bool",
        "version-missing",
        "owner",
        "credential",
        "legacy-root",
        "approve-flag",
        "counter-bool",
        "action",
        "task",
    ],
)
def test_closed_request_cannot_smuggle_authority_or_paths(configured, defect):
    client, task, body = configured
    value = copy.deepcopy(body)
    if defect == "version-bool":
        value["schema_version"] = True
    elif defect == "version-missing":
        del value["schema_version"]
    elif defect == "owner":
        value["owner_id"] = str(uuid4())
    elif defect == "credential":
        value["change"]["manifest"]["credential"] = "SYNTHETIC_CREDENTIAL_SENTINEL"
    elif defect == "legacy-root":
        value["change"]["manifest"]["root_refs"] = ["/home/SYNTHETIC_PRIVATE_LOCATOR"]
    elif defect == "approve-flag":
        value["change"]["approved"] = True
    elif defect == "counter-bool":
        value["change"]["expected_version"] = True
    elif defect == "action":
        value["change"]["manifest"]["actions"] = ["execute"]
    else:
        value["task_id"] = "SYNTHETIC_PRIVATE_LOCATOR"
    rejected = client.post(BASE + "/reviews", json=value, headers=CLI)
    assert rejected.status_code == 422 and rejected.json()["code"] == "invalid_connection_request"
    assert "SYNTHETIC_" not in rejected.text and rejected.headers["cache-control"] == "no-store"
    with psycopg.connect(task["dsn"]) as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.connection_grant_review WHERE task_id=%s", (task["task"],)
        ).fetchone() == (0,)


@pytest.mark.parametrize("defect", ["duplicate-top", "duplicate-nested", "nan", "depth", "invalid"])
def test_ambiguous_and_malformed_json_denies_without_echo(configured, defect):
    client, _, body = configured
    raw = json.dumps(body, separators=(",", ":"))
    if defect == "duplicate-top":
        raw = raw.replace('"schema_version":1', '"schema_version":1,"schema_version":1', 1)
    elif defect == "duplicate-nested":
        raw = raw.replace('"max_calls":2', '"max_calls":2,"max_calls":2')
    elif defect == "nan":
        raw = raw.replace('"max_calls":2', '"max_calls":NaN')
    elif defect == "depth":
        raw = "[" * 1500 + "0" + "]" * 1500
    else:
        raw = "SYNTHETIC_PRIVATE_LOCATOR not JSON"
    response = client.post(BASE + "/reviews", content=raw, headers={**CLI, "Content-Type": "application/json"})
    assert response.status_code == 422 and response.json()["code"] == "invalid_connection_request"
    assert "SYNTHETIC_" not in response.text


def test_host_origin_bearer_csrf_cap_and_exact_decision_digest(configured):
    client, _, body = configured
    assert client.post(BASE + "/reviews", json=body).status_code == 401
    assert client.post(BASE + "/reviews", json=body, headers={**CLI, "Host": "attacker.example"}).status_code == 403
    assert (
        client.post(BASE + "/reviews", json=body, headers={**CLI, "Origin": "https://attacker.example"}).status_code
        == 403
    )
    view = submit(client, body)
    headers = pair(client)
    assert decide(client, view, headers={"Origin": "http://127.0.0.1:8766"}).status_code == 403
    sent = {"schema_version": 1, "effect_digest": "ef" * 32, "decision": "approve"}
    assert (
        client.post(BASE + "/reviews/" + view["proposal_id"] + "/decision", json=sent, headers=headers).status_code
        == 409
    )
    sent.update(effect_digest=view["effect_digest"], approved=True)
    assert (
        client.post(BASE + "/reviews/" + view["proposal_id"] + "/decision", json=sent, headers=headers).status_code
        == 422
    )
    assert decide(client, view, headers=headers).status_code == 200
    response = client.post(
        BASE + "/reviews", content=b"x" * 65537, headers={**headers, "Content-Type": "application/json"}
    )
    assert response.status_code == 413 and response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("operation", ["propose", "preview", "decide", "current"])
def test_session_revocation_between_authorize_and_transaction_denies_all_paths(configured, monkeypatch, operation):
    client, task, body = configured
    view = submit(client, body)
    assert decide(client, view).status_code == 200
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
    if operation == "propose":
        response = client.post(BASE + "/reviews", json=body, headers=headers)
    elif operation == "preview":
        response = client.get(BASE + "/reviews/" + view["proposal_id"], headers=headers)
    elif operation == "decide":
        response = decide(client, view, headers=headers)
    else:
        response = client.get(BASE + "/grants/" + view["grant_id"], headers=headers)
    assert response.status_code == 401 and response.json()["code"] == "unauthorized"


@pytest.mark.parametrize("foreign", ["owner", "project", "manifest"])
def test_wrong_scope_is_not_found_and_never_exposes_manifest(configured, foreign):
    client, task, body = configured
    view = submit(client, body)
    if foreign == "manifest":
        body["change"]["proposal_id"] = str(uuid4())
        body["change"]["manifest"]["owner_id"] = str(uuid4())
        assert client.post(BASE + "/reviews", json=body, headers=CLI).status_code == 404
        return
    client.app.state.goal_api = GoalApi(
        CLI["Authorization"][7:],
        str(uuid4()) if foreign == "owner" else task["owner"],
        str(uuid4()) if foreign == "project" else task["project"],
        task["dsn"],
    )
    for path in ("/reviews/" + view["proposal_id"], "/grants/" + view["grant_id"]):
        response = client.get(BASE + path, headers=CLI)
        assert response.status_code == 404 and "example.com" not in response.text
    assert decide(client, view).status_code == 404


def test_current_policy_change_is_visible_and_old_review_cannot_apply(configured, tmp_path):
    client, task, body = configured
    view = submit(client, body)
    assert decide(client, view).status_code == 200
    pending_body = copy.deepcopy(body)
    pending_body["change"]["proposal_id"] = str(uuid4())
    pending = submit(client, pending_body)
    actor = Actor(task["owner"], task["project"])
    service = PolicyService(CertificateStore(tmp_path, {}))
    with psycopg.connect(task["dsn"]) as c:
        current = service.get(UnitOfWork(c), actor)
        review = service.propose(UnitOfWork(c), actor, task["task"], current.model_copy(update={"version": 2}))
    with psycopg.connect(task["dsn"]) as c:
        service.decide(UnitOfWork(c), actor, review.review_id, review.effect_digest, "approve")
    with psycopg.connect(task["dsn"]) as c:
        service.apply(UnitOfWork(c), actor, review.review_id, review.effect_digest)
    actual = client.get(BASE + "/grants/" + view["grant_id"], headers=CLI).json()
    assert actual["policy_status"] == "STALE" and actual["runtime_available"] is False
    assert decide(client, pending).status_code == 409


def test_actual_review_expiry_denies_decision_and_exposes_expired_state(configured, monkeypatch):
    from panestria.kernel.connections import ConnectionReviewService

    client, _, body = configured
    monkeypatch.setattr(routes, "_SERVICE", ConnectionReviewService(review_seconds=3))
    view = submit(client, body)
    remaining = (datetime.fromisoformat(view["review_expires_at"]) - datetime.now(UTC)).total_seconds()
    assert 0 < remaining <= 3
    time.sleep(remaining + 0.05)
    assert decide(client, view).status_code == 409
    assert client.get(BASE + "/reviews/" + view["proposal_id"], headers=CLI).json()["state"] == "EXPIRED"


def test_actual_grant_expiry_never_reports_connected_or_renews_on_replay(configured):
    client, _, body = configured
    expiry = datetime.now(UTC) + timedelta(seconds=3)
    body["change"]["manifest"]["expires_at"] = expiry.isoformat()
    view = submit(client, body)
    assert decide(client, view).status_code == 200
    time.sleep(max(0, (expiry - datetime.now(UTC)).total_seconds()) + 0.05)
    current = client.get(BASE + "/grants/" + view["grant_id"], headers=CLI).json()
    assert current["state"] == "EXPIRED" and current["runtime_available"] is False
    assert decide(client, view).json()["replayed"]
    assert client.get(BASE + "/grants/" + view["grant_id"], headers=CLI).json()["state"] == "EXPIRED"


def test_path_and_database_errors_are_bounded_redacted_and_no_store(configured, monkeypatch):
    client, _, _ = configured
    sentinel = "SYNTHETIC_PRIVATE_LOCATOR"
    response = client.get(BASE + "/grants/" + sentinel, headers=CLI)
    assert response.status_code == 422 and sentinel not in response.text

    def unavailable(*args, **kwargs):
        raise DatabaseUnavailable(sentinel)

    monkeypatch.setattr(routes, "_transaction", unavailable)
    response = client.get(BASE + "/reviews/" + str(uuid4()), headers=CLI)
    assert (
        response.status_code == 503
        and sentinel not in response.text
        and response.headers["cache-control"] == "no-store"
    )


def test_api_caller_rollback_keeps_no_orphan_review_or_event(configured, monkeypatch):
    client, task, body = configured
    original = routes._SERVICE.propose

    def refuse_after_write(*args, **kwargs):
        original(*args, **kwargs)
        raise KernelDenied("connection_expiry_invalid")

    with monkeypatch.context() as patch:
        patch.setattr(routes._SERVICE, "propose", refuse_after_write)
        assert client.post(BASE + "/reviews", json=body, headers=CLI).status_code == 422
    with psycopg.connect(task["dsn"]) as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.connection_grant_review WHERE task_id=%s", (task["task"],)
        ).fetchone() == (0,)
        assert c.execute(
            "SELECT count(*) FROM panestria.task_event WHERE task_id=%s AND kind LIKE 'connection.%%'", (task["task"],)
        ).fetchone() == (0,)
    assert submit(client, body)["state"] == "PENDING"


def test_health_only_does_not_expose_review_api():
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
    assert client.post(BASE + "/reviews", json={}, headers=CLI).status_code == 404
