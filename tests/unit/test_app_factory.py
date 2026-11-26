"""The app factory: features mount in profile order; a failed mount leaves nothing running."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from panestria.api.app import AppProfile, Middleware, State, build_app
from panestria.api.auth import GoalApi
from panestria.api.health import HealthService
from panestria.config import Settings

DSN = "postgresql://panestria_synthetic:placeholder-not-a-secret@127.0.0.1:1/panestria_synthetic"
SCOPE = GoalApi("synthetic-loopback-token", "owner", "project", DSN)


def _settings() -> Any:
    return Settings(database_url=DSN).validate_profile()


class _Tag:
    """Middleware that records the order it sees a request in."""

    def __init__(self, app: Any, name: str) -> None:
        self.app, self.name = app, name

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            scope.setdefault("state", {}).setdefault("seen", []).append(self.name)
        await self.app(scope, receive, send)


class _Fails:
    def mount(self, app: FastAPI) -> None:
        raise RuntimeError("feature_failed")


def test_features_mount_in_order_and_later_middleware_wraps_earlier() -> None:
    profile = AppProfile(
        _settings(),
        SCOPE,
        (State("marker", 1), Middleware(_Tag, {"name": "inner"}), Middleware(_Tag, {"name": "outer"})),
    )
    app = build_app(profile)
    try:
        assert app.state.goal_api is SCOPE and app.state.marker == 1

        @app.get("/seen")
        def seen(request: Request) -> list[str]:
            return list(request.state.seen)

        response = TestClient(app, base_url="http://127.0.0.1:8765").get("/seen")
        assert response.json() == ["outer", "inner"]
    finally:
        app.state.health.shutdown()


def test_a_profile_without_scope_is_health_only() -> None:
    app = build_app(AppProfile(_settings()))
    try:
        assert app.state.goal_api is None
        assert {getattr(route, "path", None) for route in app.routes} == {"/healthz", "/readyz"}
    finally:
        app.state.health.shutdown()


def test_a_failed_feature_shuts_the_health_service_down(monkeypatch: pytest.MonkeyPatch) -> None:
    stopped: list[bool] = []
    original = HealthService.shutdown

    def record(self: HealthService) -> None:
        stopped.append(True)
        original(self)

    monkeypatch.setattr(HealthService, "shutdown", record)
    with pytest.raises(RuntimeError, match="feature_failed"):
        build_app(AppProfile(_settings(), SCOPE, (State("marker", 1), _Fails())))
    assert stopped == [True]
