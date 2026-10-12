"""HTTP application factory for liveness and readiness."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from panestria import package_version
from panestria.api.health import (
    ErrorBody,
    HealthService,
    Liveness,
    Readiness,
    ReadinessProbe,
    SecretBearingOutputRejected,
    secret_rejection_body,
)
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
    async def lifespan(app: FastAPI):
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
