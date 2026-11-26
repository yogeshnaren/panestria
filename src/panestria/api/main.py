"""HTTP application factory for liveness and readiness."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from panestria import package_version
from panestria.api.auth import GoalApi, LoopbackDenied, authorize, error_body
from panestria.api.health import (
    ErrorBody,
    HealthService,
    Liveness,
    Readiness,
    ReadinessProbe,
    SecretBearingOutputRejected,
    secret_rejection_body,
)
from panestria.api.routes.activity import router as activity_router
from panestria.api.routes.approvals import router as approvals_router
from panestria.api.routes.artifacts import router as artifacts_router
from panestria.api.routes.connections import router as connections_router
from panestria.api.routes.events import router as events_router
from panestria.api.routes.goals import router as goals_router
from panestria.api.routes.quota import router as quota_router
from panestria.config import Settings, ValidatedSettings


def create_app(settings: Settings | ValidatedSettings, readiness_probe: ReadinessProbe) -> FastAPI:
    if isinstance(settings, ValidatedSettings):
        validated = settings
    elif isinstance(settings, Settings):
        validated = settings.validate_profile()
    else:
        raise TypeError("settings must be the panestria settings model")
    service = HealthService(validated, readiness_probe)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        del app
        yield
        service.shutdown()

    app = FastAPI(
        title="panestria",
        version=package_version(),
        debug=False,
        docs_url=None,
        redoc_url=None,
        # The schema is published as docs/api/openapi.json; serving it would
        # describe every route to any local caller before authentication.
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = validated
    app.state.health = service
    app.state.goal_api = None

    @app.exception_handler(RequestValidationError)
    def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Authenticate before describing the rejected input. Field-level
        # validation detail is never returned; it would map the API surface.
        del exc
        api = getattr(request.app.state, "goal_api", None)
        if isinstance(api, GoalApi):
            try:
                authorize(request, api)
            except LoopbackDenied as denied:
                return JSONResponse(status_code=denied.status_code, content=error_body(denied.code))
        return JSONResponse(status_code=422, content=error_body("invalid_request"))

    @app.get("/healthz", response_model=Liveness)
    def healthz() -> Liveness:
        return service.liveness()

    @app.get(
        "/readyz",
        response_model=Readiness,
        responses={503: {"model": Readiness}, 500: {"model": ErrorBody}},
    )
    def readyz() -> JSONResponse:
        deadline = datetime.now(timezone.utc) + timedelta(milliseconds=validated.readiness_budget_ms)
        try:
            body = service.readiness(deadline)
        except SecretBearingOutputRejected:
            rejected = secret_rejection_body(str(uuid4()))
            return JSONResponse(status_code=500, content=rejected.model_dump(mode="json"))
        status_code = 200 if body.status == "ready" else 503
        return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))

    return app


def mount_goal_api(app: FastAPI, goal_api: GoalApi) -> None:
    """Attach scoped goal routes. Health-only apps leave them unmounted."""
    app.state.goal_api = goal_api
    mount_goal_routes(app)
    mount_activity_api(app)


def mount_goal_routes(app: FastAPI) -> None:
    """The goal, event, approval, artifact, quota, connection and Build review routes."""
    if not isinstance(app.state.goal_api, GoalApi):
        raise TypeError("goal routes require configured actor scope")
    app.include_router(goals_router)
    app.include_router(events_router)
    app.include_router(approvals_router)
    app.include_router(artifacts_router)
    app.include_router(quota_router)
    app.include_router(connections_router)
    from panestria.api.routes.mission_review import router as mission_review_router

    app.include_router(mission_review_router)


def mount_activity_api(app: FastAPI, *, dependencies: Sequence[Any] = ()) -> None:
    """Mount only content-free observations, without goal/merge/tool endpoints."""
    if not isinstance(app.state.goal_api, GoalApi):
        raise TypeError("activity API requires configured actor scope")
    from panestria.api.routes.build_observation import router as build_observation_router

    app.include_router(activity_router, dependencies=list(dependencies))
    app.include_router(build_observation_router, dependencies=list(dependencies))
    from panestria.api.routes.mission_review import capabilities

    app.include_router(capabilities, dependencies=list(dependencies))


def mount_browser_api(app: FastAPI, access: object) -> None:
    from panestria.api.routes.sessions import router
    from panestria.api.security import BrowserSecurity
    from panestria.api.sessions import BrowserAccess

    if not isinstance(access, BrowserAccess) or not isinstance(app.state.goal_api, GoalApi):
        raise TypeError("browser API requires configured actor scope")
    if access.database_url != app.state.goal_api.database_url:
        raise ValueError("browser_database_scope_mismatch")
    app.state.browser_access = access
    app.add_middleware(BrowserSecurity, access=access)
    app.include_router(router)


def mount_browser_scopes(app: FastAPI, scopes: object) -> None:
    """Several browser session scopes on one origin; pairing and logout under /v1/session/{scope}."""
    from panestria.api.routes.sessions import scoped_router
    from panestria.api.security import BrowserSecurity
    from panestria.api.sessions import SESSION_SCOPES, AcceptScopes, BrowserScopes

    if not isinstance(scopes, BrowserScopes) or not isinstance(app.state.goal_api, GoalApi):
        raise TypeError("browser scopes require configured actor scope")
    if scopes.database_url != app.state.goal_api.database_url:
        raise ValueError("browser_database_scope_mismatch")
    if getattr(app.state, "browser_access", None) is not None:
        raise ValueError("browser_scope_conflict")
    app.state.browser_scopes = scopes
    # Every scope shares the origin, so one envelope checks host, origin and limits for all.
    app.add_middleware(BrowserSecurity, access=scopes["activity"])
    for scope in SESSION_SCOPES:
        app.include_router(scoped_router, prefix=f"/v1/session/{scope}", dependencies=[Depends(AcceptScopes(scope))])


def mount_ask_api(app: FastAPI, ask: object, *, dependencies: Sequence[Any] = ()) -> None:
    from panestria.api.routes.ask import AskApi, router
    from panestria.api.routes.learning import router as learning_router
    from panestria.api.routes.memory import router as memory_router
    from panestria.api.routes.memory_v2 import router as memory_v2_router

    if not isinstance(ask, AskApi) or not isinstance(app.state.goal_api, GoalApi):
        raise TypeError("Ask requires configured scope and a local provider")
    app.state.ask_api = ask
    for included in (router, learning_router, memory_router, memory_v2_router):
        app.include_router(included, dependencies=list(dependencies))


def mount_profile_api(app: FastAPI, profiles: object) -> None:
    from panestria.api.routes.profiles import ProfileApi, router

    if not isinstance(profiles, ProfileApi) or not isinstance(app.state.goal_api, GoalApi):
        raise TypeError("profiles require configured owner scope and a trusted vault")
    app.state.profile_api = profiles
    app.include_router(router)
