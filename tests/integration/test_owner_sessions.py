"""Owner app session scopes on real PostgreSQL: each scope pairs, authenticates and logs out alone.

The model, hardware and Build run service are not exercised. No lifespan runs,
so no model starts. Every request below is decided by authentication alone.
"""

from __future__ import annotations

import hashlib
import socket
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_local_server import configuration

from panestria.api.app import build_app
from panestria.api.owner import owner_profile
from panestria.api.sessions import SESSION_SCOPES
from panestria.config import Settings
from panestria.config_local import load_local_settings
from panestria.kernel.local_setup import LocalSetupIntent, LocalSetupService
from panestria.kernel.uow import UnitOfWork


class _StubRun:
    """Stands in for MissionRunService; only its presence and review root are used here."""

    root: Path

    def __init__(self, path: Path, actor: object, dsn: str) -> None:
        del path, actor, dsn
        self.settings = SimpleNamespace(root=_StubRun.root)
        self.configuration = hashlib.sha256(b"owner-sessions").hexdigest()

    def close(self) -> None:
        pass


@dataclass
class Owner:
    app: FastAPI
    origin: str
    token: str

    def client(self) -> TestClient:
        return TestClient(self.app, base_url=self.origin)


@dataclass(frozen=True)
class Session:
    cookie_name: str
    token: str
    csrf: str

    def headers(self, *, csrf: str | None = None, origin: str | None = None) -> dict[str, str]:
        headers = {"Cookie": f"{self.cookie_name}={self.token}"}
        if csrf is not None:
            headers["X-Panestria-CSRF"] = csrf
        if origin is not None:
            headers["Origin"] = origin
        return headers


def _app(r1_database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Owner:
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    path, _ = configuration(tmp_path, port=port)
    config, token = load_local_settings(path)
    with psycopg.connect(r1_database) as db:
        LocalSetupService().initialize(
            UnitOfWork(db),
            LocalSetupIntent(owner_id=config.owner_id, project_id=config.project_id, intent="OFFLINE_ASK"),
        )
    review = tmp_path / "review"
    (review / "reports").mkdir(parents=True, mode=0o700)
    review.chmod(0o700)
    _StubRun.root = review
    monkeypatch.setattr("panestria.execution.mission_run.MissionRunService", _StubRun)
    monkeypatch.setattr("panestria.api.routes.mission_run.MissionRunService", _StubRun)
    assets = tmp_path / "assets"
    assets.mkdir(mode=0o700)
    for name, body in (("index.html", b'<div id="root"></div>'), ("mission.js", b";"), ("mission.css", b"*{}")):
        (assets / name).write_bytes(body)
    settings = Settings(database_url=r1_database).validate_profile()
    secret = token.get_secret_value()
    profile = owner_profile(config, settings, secret, assets, build_run=tmp_path / "build.json")
    return Owner(build_app(profile), config.origin, secret)


@pytest.fixture
def owner(r1_database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Owner]:
    application = _app(r1_database, tmp_path, monkeypatch)
    yield application
    application.app.state.health.shutdown()


def _code(owner: Owner, scope: str) -> str:
    response = owner.client().post(
        f"/v1/session/{scope}/code", headers={"Authorization": f"Bearer {owner.token}"}, json={}
    )
    assert response.status_code == 200, response.text
    return str(response.json()["code"])


def _pair(owner: Owner, scope: str, code: str) -> Any:
    return owner.client().post(f"/v1/session/{scope}/pair", headers={"Origin": owner.origin}, json={"code": code})


def _session(owner: Owner, scope: str) -> Session:
    response = _pair(owner, scope, _code(owner, scope))
    assert response.status_code == 200, response.text
    (name, value), *rest = [(k, v) for k, v in response.cookies.items()]
    assert not rest and name.startswith(f"panestria_owner_{scope}_")
    return Session(name, value, response.json()["csrf_token"])


def test_each_scope_pairs_separately_and_a_code_works_only_for_its_scope(owner: Owner) -> None:
    ask_code, build_code = _code(owner, "ask"), _code(owner, "build")
    # A Build code is not an Ask code, and issuing it left the Ask code valid.
    assert _pair(owner, "ask", build_code).json()["code"] == "invalid_pairing_code"
    assert _pair(owner, "ask", ask_code).status_code == 200
    assert _pair(owner, "build", build_code).status_code == 200
    # The single-mode routes are not mounted in the owner app.
    bearer = {"Authorization": f"Bearer {owner.token}"}
    assert owner.client().post("/v1/session/code", headers=bearer, json={}).status_code == 404


def test_a_session_reaches_only_the_routes_its_scope_accepts(owner: Owner) -> None:
    sessions = {scope: _session(owner, scope) for scope in SESSION_SCOPES}
    client = owner.client()
    ask_request, plan, goal = str(uuid4()), str(uuid4()), str(uuid4())
    for scope, session in sessions.items():
        # Every scope may observe.
        assert client.get("/v1/activity", headers=session.headers()).status_code == 200, scope
        assert client.get("/v1/mission/capabilities", headers=session.headers()).status_code == 200, scope
        ask = client.get(f"/v1/ask/{ask_request}", headers=session.headers())
        build = client.get(f"/v1/mission/build/plans/{plan}", headers=session.headers())
        review = client.get(f"/v1/mission/goals/{goal}/build-review", headers=session.headers())
        run = client.get(f"/v1/mission/build/plans/{plan}/run", headers=session.headers())
        if scope == "ask":
            assert ask.status_code == 404, ask.text  # Authenticated; no such request.
        else:
            assert (ask.status_code, ask.json()["code"]) == (403, "session_scope_denied"), scope
        for response in (build, review):
            if scope == "build":
                assert response.status_code not in (401, 403), response.text
            else:
                assert (response.status_code, response.json()["code"]) == (403, "session_scope_denied"), scope
        if scope != "build":
            assert (run.status_code, run.json()["code"]) == (403, "session_scope_denied"), scope


def test_a_session_token_renamed_into_another_scope_cookie_is_refused(owner: Owner) -> None:
    ask, build = _session(owner, "ask"), _session(owner, "build")
    stolen = Session(build.cookie_name, ask.token, ask.csrf)
    response = owner.client().get(f"/v1/mission/build/plans/{uuid4()}", headers=stolen.headers())
    assert (response.status_code, response.json()["code"]) == (401, "unauthorized")


def test_a_mutation_needs_that_scope_cookie_and_that_scope_csrf(owner: Owner) -> None:
    ask, build = _session(owner, "ask"), _session(owner, "build")
    client, path = owner.client(), f"/v1/ask/{uuid4()}/cancel"
    with_build = client.post(path, headers=build.headers(csrf=build.csrf, origin=owner.origin), json={})
    assert (with_build.status_code, with_build.json()["code"]) == (403, "session_scope_denied")
    wrong_csrf = client.post(path, headers=ask.headers(csrf=build.csrf, origin=owner.origin), json={})
    assert (wrong_csrf.status_code, wrong_csrf.json()["code"]) == (403, "csrf_denied")
    right = client.post(path, headers=ask.headers(csrf=ask.csrf, origin=owner.origin), json={})
    assert right.status_code == 404, right.text  # Authenticated; no such request.


def test_with_every_cookie_present_each_route_uses_its_own_scope(owner: Owner) -> None:
    sessions = [_session(owner, scope) for scope in SESSION_SCOPES]
    cookie = {"Cookie": "; ".join(f"{s.cookie_name}={s.token}" for s in sessions)}
    client = owner.client()
    assert client.get(f"/v1/ask/{uuid4()}", headers=cookie).status_code == 404
    assert client.get(f"/v1/mission/build/plans/{uuid4()}", headers=cookie).status_code not in (401, 403)


def test_logging_out_one_scope_leaves_the_others_paired(owner: Owner) -> None:
    ask, build = _session(owner, "ask"), _session(owner, "build")
    client = owner.client()
    logout = client.post("/v1/session/ask/logout", headers=ask.headers(csrf=ask.csrf, origin=owner.origin), json={})
    assert logout.status_code == 200, logout.text
    assert client.get("/v1/activity", headers=ask.headers()).json()["code"] == "unauthorized"
    assert client.get("/v1/activity", headers=build.headers()).status_code == 200


def test_pairing_attempts_share_one_budget_across_scopes(owner: Owner) -> None:
    statuses = [_pair(owner, SESSION_SCOPES[i % 3], "0" * 8).status_code for i in range(6)]
    assert statuses[:5] == [401] * 5 and statuses[5] == 429
