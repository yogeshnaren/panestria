"""HTTP application factory for liveness and readiness."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from panestria import package_version
from panestria.api.auth import GoalApi
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
        lifespan=lifespan,
    )
    app.state.settings = validated
    app.state.health = service
    app.state.goal_api = None

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
    app.include_router(goals_router)
    app.include_router(events_router)
    app.include_router(approvals_router)
    app.include_router(artifacts_router)
    app.include_router(quota_router)
    app.include_router(connections_router)
    from panestria.api.routes.mission_review import router as mission_review_router

    app.include_router(mission_review_router)
    mount_activity_api(app)


def mount_activity_api(app: FastAPI) -> None:
    """Mount only content-free observations, without goal/merge/tool endpoints."""
    if not isinstance(app.state.goal_api, GoalApi):
        raise TypeError("activity API requires configured actor scope")
    from panestria.api.routes.build_observation import router as build_observation_router

    app.include_router(activity_router)
    app.include_router(build_observation_router)
    from panestria.api.routes.mission_review import capabilities

    app.include_router(capabilities)


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


def mount_ask_api(app: FastAPI, ask: object) -> None:
    from panestria.api.routes.ask import AskApi, router
    from panestria.api.routes.learning import router as learning_router
    from panestria.api.routes.memory import router as memory_router
    from panestria.api.routes.memory_v2 import router as memory_v2_router

    if not isinstance(ask, AskApi) or not isinstance(app.state.goal_api, GoalApi):
        raise TypeError("Ask requires configured scope and a local provider")
    app.state.ask_api = ask
    app.include_router(router)
    app.include_router(learning_router)
    app.include_router(memory_router)
    app.include_router(memory_v2_router)


def mount_profile_api(app: FastAPI, profiles: object) -> None:
    from panestria.api.routes.profiles import ProfileApi, router

    if not isinstance(profiles, ProfileApi) or not isinstance(app.state.goal_api, GoalApi):
        raise TypeError("profiles require configured owner scope and a trusted vault")
    app.state.profile_api = profiles
    app.include_router(router)
