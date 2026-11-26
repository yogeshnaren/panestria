"""One factory for every product server: a profile says what to mount.

A server mode is an ``AppProfile``: validated settings, the owner/project scope
and an ordered tuple of features. ``build_app`` creates the health-only base
app (``main.create_app``), records the scope and mounts each feature in order.
The order is part of the surface. It fixes route matching and middleware
nesting, and ``tests/unit/test_app_profiles.py`` pins it for every mode.

A feature is anything with ``mount(app)``. The general ones are here; the
Mission Control parts are in ``mission_web.py`` and the local Ask runtime is in
``local_server.py``. A feature with routes takes ``scope``: on an app with
browser session scopes (``ScopedBrowser``), its routes accept only sessions
paired for those scopes. Single-mode servers leave it empty.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Protocol

from fastapi import APIRouter, Depends, FastAPI

from panestria.api.auth import GoalApi
from panestria.api.health import ReadinessProbe, default_readiness_probe
from panestria.api.main import (
    create_app,
    mount_activity_api,
    mount_ask_api,
    mount_browser_api,
    mount_browser_scopes,
    mount_goal_routes,
    mount_profile_api,
)
from panestria.api.sessions import AcceptScopes, BrowserScopes, SessionScope
from panestria.config import ValidatedSettings


class Feature(Protocol):
    def mount(self, app: FastAPI) -> None: ...


@dataclass(frozen=True)
class AppProfile:
    settings: ValidatedSettings
    scope: GoalApi | None = None
    features: tuple[Feature, ...] = ()
    readiness_probe: ReadinessProbe = default_readiness_probe


def build_app(profile: AppProfile) -> FastAPI:
    app = create_app(profile.settings, profile.readiness_probe)
    try:
        if profile.scope is not None:
            app.state.goal_api = profile.scope
        mount(app, profile.features)
    except BaseException:
        app.state.health.shutdown()
        raise
    return app


def mount(app: FastAPI, features: Iterable[Feature]) -> None:
    for feature in features:
        feature.mount(app)


def scope_dependencies(scope: tuple[SessionScope, ...]) -> list[Any]:
    """The route dependency that admits only sessions for ``scope``; none when unscoped."""
    return [Depends(AcceptScopes(*scope))] if scope else []


@dataclass(frozen=True)
class GoalRoutes:
    """The scoped goal, event, approval, artifact, quota, connection and Build review routes."""

    def mount(self, app: FastAPI) -> None:
        mount_goal_routes(app)


@dataclass(frozen=True)
class Activity:
    """Content-free observations only: no goal, merge or tool endpoints."""

    scope: tuple[SessionScope, ...] = ()

    def mount(self, app: FastAPI) -> None:
        mount_activity_api(app, dependencies=scope_dependencies(self.scope))


@dataclass(frozen=True)
class Ask:
    api: Any  # AskApi; imported lazily by main.mount_ask_api
    scope: tuple[SessionScope, ...] = ()

    def mount(self, app: FastAPI) -> None:
        mount_ask_api(app, self.api, dependencies=scope_dependencies(self.scope))


@dataclass(frozen=True)
class Profiles:
    api: Any  # ProfileApi

    def mount(self, app: FastAPI) -> None:
        mount_profile_api(app, self.api)


@dataclass(frozen=True)
class Browser:
    """Cookie sessions for one browser scope, behind the same-origin envelope."""

    access: Any  # BrowserAccess

    def mount(self, app: FastAPI) -> None:
        mount_browser_api(app, self.access)


@dataclass(frozen=True)
class ScopedBrowser:
    """One cookie session per scope on one origin, behind the same-origin envelope."""

    scopes: BrowserScopes

    def mount(self, app: FastAPI) -> None:
        mount_browser_scopes(app, self.scopes)


@dataclass(frozen=True)
class ConnectionReviews:
    """Connection declaration review from the terminal; never with a dashboard."""

    def mount(self, app: FastAPI) -> None:
        from panestria.api.routes.connections import router

        app.state.connection_terminal_only = True
        app.include_router(router)


@dataclass(frozen=True)
class Storage:
    """Owner host storage observations; the observer is closed with the app."""

    observer: Any  # StorageObserver

    def mount(self, app: FastAPI) -> None:
        observer = self.observer
        app.state.storage_observer = observer

        @asynccontextmanager
        async def storage_lifecycle(_: FastAPI) -> AsyncIterator[None]:
            try:
                yield
            finally:
                observer.close()

        app.include_router(APIRouter(lifespan=storage_lifecycle))


@dataclass(frozen=True)
class State:
    """One fixed ``app.state`` value that routes read."""

    name: str
    value: Any

    def mount(self, app: FastAPI) -> None:
        setattr(app.state, self.name, self.value)


@dataclass(frozen=True)
class Middleware:
    """An ASGI middleware. Each one added wraps everything added before it."""

    cls: Any
    options: dict[str, Any] = field(default_factory=dict)

    def mount(self, app: FastAPI) -> None:
        app.add_middleware(self.cls, **self.options)
