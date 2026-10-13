"""Browser session scope, single-use pairing and revocation on PostgreSQL."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest

from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.sessions import SessionService
from panestria.kernel.uow import UnitOfWork


def test_pairing_and_secret_redaction(r1_task: dict[str, str], record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-009-TC02")
    record_property("source_clauses", "AOS-009-F01,AOS-009-F03")
    service, actor = SessionService(b"test-only-key-not-a-real-secret!!"), Actor(r1_task["owner"], r1_task["project"])
    with psycopg.connect(r1_task["dsn"]) as c:
        old = service.issue_pairing_code(UnitOfWork(c), actor)
        c.commit()
        code = service.issue_pairing_code(UnitOfWork(c), actor)
        c.commit()
        with pytest.raises(KernelDenied, match="invalid_pairing_code"), c.transaction():
            service.pair(UnitOfWork(c), actor, old)
        with pytest.raises(KernelDenied, match="invalid_pairing_code"), c.transaction():
            service.pair(UnitOfWork(c), Actor(str(uuid4()), actor.project_id), code)

    def pair() -> object:
        try:
            with psycopg.connect(r1_task["dsn"]) as c:
                return service.pair(UnitOfWork(c), actor, code)
        except KernelDenied as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: pair(), range(2)))
    assert results.count("invalid_pairing_code") == 1
    tokens = next(value for value in results if value != "invalid_pairing_code")
    assert tokens.token not in repr(tokens) and tokens.csrf not in repr(tokens)
    with psycopg.connect(r1_task["dsn"]) as c:
        assert service.authenticate(UnitOfWork(c), actor, tokens.token) == tokens.session_id
        for supplied in [None, "bad", ""]:
            with pytest.raises(KernelDenied, match="csrf_denied"), c.transaction():
                service.authenticate(UnitOfWork(c), actor, tokens.token, csrf=supplied, mutation=True)
        service.authenticate(UnitOfWork(c), actor, tokens.token, csrf=tokens.csrf, mutation=True)
        c.commit()
        persisted = str(
            c.execute(
                "SELECT token_hash,csrf_hash FROM panestria.browser_session WHERE id=%s", (tokens.session_id,)
            ).fetchall()
        )
        persisted += str(
            c.execute(
                "SELECT code_hash FROM panestria.pairing_challenge WHERE project_id=%s", (actor.project_id,)
            ).fetchall()
        )
        assert all(secret not in persisted for secret in [code, old, tokens.token, tokens.csrf])
        service.revoke(UnitOfWork(c), actor, tokens.token, tokens.csrf)
        c.commit()
        with pytest.raises(KernelDenied, match="unauthorized"), c.transaction():
            service.authenticate(UnitOfWork(c), actor, tokens.token)
        with pytest.raises(KernelDenied, match="unauthorized"), c.transaction():
            service.authenticate(UnitOfWork(c), actor, tokens.token, csrf=tokens.csrf, mutation=True)


def test_session_expiry_and_other_project(r1_task: dict[str, str]) -> None:
    service, actor = SessionService(b"test-only-key-not-a-real-secret!!"), Actor(r1_task["owner"], r1_task["project"])
    with psycopg.connect(r1_task["dsn"]) as c:
        code = service.issue_pairing_code(UnitOfWork(c), actor)
        c.commit()
        tokens = service.pair(UnitOfWork(c), actor, code)
        c.commit()
        with pytest.raises(KernelDenied, match="unauthorized"), c.transaction():
            service.authenticate(UnitOfWork(c), Actor(actor.owner_id, str(uuid4())), tokens.token)
        c.execute(
            "UPDATE panestria.browser_session SET expires_at=clock_timestamp()-interval '1 second' WHERE id=%s",
            (tokens.session_id,),
        )
        c.commit()
        with pytest.raises(KernelDenied, match="unauthorized"), c.transaction():
            service.authenticate(UnitOfWork(c), actor, tokens.token)
        code = service.issue_pairing_code(UnitOfWork(c), actor)
        c.commit()
        c.execute(
            "UPDATE panestria.pairing_challenge SET expires_at=clock_timestamp()-interval '1 second'"
            " WHERE owner_id=%s AND project_id=%s",
            (actor.owner_id, actor.project_id),
        )
        c.commit()
        with pytest.raises(KernelDenied, match="invalid_pairing_code"), c.transaction():
            service.pair(UnitOfWork(c), actor, code)


def _client(task: dict[str, str]) -> object:
    from fastapi.testclient import TestClient

    from panestria.api.auth import GoalApi
    from panestria.api.main import create_app, mount_browser_api, mount_goal_api
    from panestria.api.sessions import BrowserAccess
    from panestria.config import Settings

    app = create_app(Settings(database_url=task["dsn"], bind_port=8766), lambda _deadline: None)
    mount_goal_api(app, GoalApi("test-only-cli-token-at-least-16", task["owner"], task["project"], task["dsn"]))
    mount_browser_api(
        app, BrowserAccess("http://127.0.0.1:8766", SessionService(b"test-only-key-not-a-real-secret!!"), task["dsn"])
    )
    return TestClient(app, base_url="http://127.0.0.1:8766")


def test_origin_host_csrf_matrix(r1_task: dict[str, str], record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-009-TC01")
    record_property("source_clauses", "AOS-009-F01,AOS-009-F03,AOS-009-F04,AOS-009-AC01,AOS-009-AC03")
    client = _client(r1_task)
    cli = {"Authorization": "Bearer test-only-cli-token-at-least-16"}
    origin = {"Origin": "http://127.0.0.1:8766"}
    assert client.get("/healthz", headers={"Host": "rebind.attacker.example:8766"}).status_code == 403
    code_response = client.post("/v1/session/code", json={}, headers=cli)
    assert code_response.status_code == 200
    code = code_response.json()["code"]
    assert (
        client.post("/v1/session/pair", json={"code": code}, headers={"Origin": "https://evil.example"}).status_code
        == 403
    )
    assert client.post("/v1/session/pair", json={"code": code}).status_code == 403
    paired = client.post("/v1/session/pair", json={"code": code}, headers=origin)
    assert paired.status_code == 200
    cookie = paired.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/v1" in cookie
    csrf = paired.json()["csrf_token"]
    assert client.get(f"/v1/goals/{r1_task['goal']}").status_code == 200  # same-origin GET need not send Origin
    assert client.post("/v1/goals", json={}, headers=origin).status_code == 403
    assert client.post("/v1/goals", json={}, headers={**origin, "X-Panestria-CSRF": "wrong"}).status_code == 403
    verified = client.post(
        "/v1/goals", json={}, headers={**origin, "X-Panestria-CSRF": csrf, "Idempotency-Key": "empty"}
    )
    assert verified.status_code == 422 and verified.json()["code"] == "invalid_contract"
    assert client.get(f"/v1/goals/{r1_task['goal']}", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.get(f"/v1/goals/{r1_task['goal']}", headers={"Referer": "https://evil.example/"}).status_code == 403
    assert client.post("/v1/session/pair", json={"code": code}, headers=origin).status_code == 401
    assert (
        client.post("/v1/session/pair", content="{}", headers={**origin, "Content-Type": "text/plain"}).status_code
        == 415
    )
    assert (
        client.post(
            "/v1/goals", content=b"x" * 65537, headers={**origin, "Content-Type": "application/json"}
        ).status_code
        == 413
    )
    assert client.get("/healthz?token=forbidden").status_code == 400
    for response in [paired, verified]:
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
        assert "access-control-allow-origin" not in response.headers
    revoked = client.post("/v1/session/logout", json={}, headers={**origin, "X-Panestria-CSRF": csrf})
    assert revoked.status_code == 200
    assert client.get(f"/v1/goals/{r1_task['goal']}").status_code == 401
    assert client.get(f"/v1/goals/{r1_task['goal']}", headers=cli).status_code == 200


def test_pairing_rate_and_closed_body(r1_task: dict[str, str]) -> None:
    client = _client(r1_task)
    origin = {"Origin": "http://127.0.0.1:8766"}
    assert (
        client.post("/v1/session/pair", json={"code": "00000000", "approved": True}, headers=origin).status_code == 422
    )
    for _ in range(4):
        assert client.post("/v1/session/pair", json={"code": "00000000"}, headers=origin).status_code == 401
    assert client.post("/v1/session/pair", json={"code": "00000000"}, headers=origin).status_code == 429


def test_mutation_and_revocation_share_one_transaction(
    r1_task: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import json
    import threading
    from pathlib import Path

    from panestria.api.routes import goals
    from panestria.api.sessions import COOKIE_NAME

    client = _client(r1_task)
    cli = {"Authorization": "Bearer test-only-cli-token-at-least-16"}
    origin = {"Origin": "http://127.0.0.1:8766"}
    code = client.post("/v1/session/code", json={}, headers=cli).json()["code"]
    paired = client.post("/v1/session/pair", json={"code": code}, headers=origin)
    headers = {
        **origin,
        "X-Panestria-CSRF": paired.json()["csrf_token"],
        "Cookie": f"{COOKIE_NAME}={client.cookies.get(COOKIE_NAME)}",
        "Idempotency-Key": "session-race",
    }
    body = json.loads((Path(__file__).resolve().parents[2] / "docs/fixtures/synthetic-goal-contract.json").read_text())
    body.update(owner_id=r1_task["owner"], project_id=r1_task["project"], goal_id=str(uuid4()))
    entered, release, revoke_entered = threading.Event(), threading.Event(), threading.Event()
    original_submit = goals._SERVICE.submit
    original_revoke = SessionService.revoke

    def submit(*args: object, **kwargs: object) -> object:
        entered.set()
        assert release.wait(2)
        return original_submit(*args, **kwargs)

    def revoke(*args: object, **kwargs: object) -> object:
        revoke_entered.set()
        return original_revoke(*args, **kwargs)

    monkeypatch.setattr(goals._SERVICE, "submit", submit)
    monkeypatch.setattr(SessionService, "revoke", revoke)
    with ThreadPoolExecutor(max_workers=2) as pool:
        mutation = pool.submit(client.post, "/v1/goals", json=body, headers=headers)
        assert entered.wait(2)
        logout = pool.submit(client.post, "/v1/session/logout", json={}, headers=headers)
        assert revoke_entered.wait(2)
        assert not logout.done()
        release.set()
        assert mutation.result(timeout=3).status_code == 202
        assert logout.result(timeout=3).status_code == 200
    client.cookies.clear()
    assert client.get(f"/v1/goals/{body['goal_id']}", headers={"Cookie": headers["Cookie"]}).status_code == 401
