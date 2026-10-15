"""Same-origin owner review of the fixed synthetic native demo."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import psycopg
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from panestria.api.auth import GoalApi
from panestria.api.routes.sessions import logout, pair
from panestria.api.security import BrowserSecurity
from panestria.api.sessions import BrowserAccess
from panestria.execution.proposal_demo import DemoUnavailable, ProposalDemo
from panestria.kernel.errors import KernelDenied
from panestria.kernel.sessions import SessionService

ASSETS = Path(__file__).with_name("demo_assets")


class StartBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    goal_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    certificate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class DecisionBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    goal_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    approval_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    effect_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_version: int = Field(ge=0)
    decision: str = Field(pattern=r"^(approve|deny)$")
    idempotency_key: str = Field(pattern=r"^[0-9a-f-]{36}$")


class CancelBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    goal_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    expected_version: int = Field(ge=0)


def create_demo_app(demo: ProposalDemo, origin: str) -> FastAPI:
    access = BrowserAccess(origin, SessionService(bytes.fromhex(demo.identity["session_secret"])), demo.dsn)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        demo.close()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.browser_access = access
    # Reuse the existing pairing routes without mounting the general goal API.
    app.state.goal_api = GoalApi("unused-demo-cli-token", demo.actor.owner_id, demo.actor.project_id, demo.dsn)
    app.add_api_route("/v1/session/pair", pair, methods=["POST"])
    app.add_api_route("/v1/session/logout", logout, methods=["POST"])
    app.add_middleware(BrowserSecurity, access=access)

    @app.exception_handler(DemoUnavailable)
    async def unavailable(request: Request, exc: DemoUnavailable) -> JSONResponse:
        return JSONResponse({"code": str(exc)}, status_code=409)

    @app.exception_handler(KernelDenied)
    async def denied(request: Request, exc: KernelDenied) -> JSONResponse:
        return JSONResponse({"code": exc.code}, status_code=403)

    @app.exception_handler(psycopg.Error)
    async def database(request: Request, exc: psycopg.Error) -> JSONResponse:
        return JSONResponse({"code": "database_unavailable"}, status_code=503)

    def auth(request: Request, connection: psycopg.Connection[Any] | None = None) -> None:
        access.authenticate(request, demo.actor, connection)

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(ASSETS / "index.html", media_type="text/html")

    @app.get("/demo.js")
    def javascript() -> FileResponse:
        return FileResponse(ASSETS / "demo.js", media_type="application/javascript")

    @app.get("/demo.css")
    def css() -> FileResponse:
        return FileResponse(ASSETS / "demo.css", media_type="text/css")

    @app.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "alive", "scope": "fixed-public-native-demo"}

    @app.get("/v1/demo")
    def state(request: Request) -> dict[str, Any]:
        auth(request)
        return demo.view()

    @app.post("/v1/demo/start")
    def start(request: Request, body: StartBody) -> dict[str, bool]:
        auth(request)
        return {
            "started": demo.start(
                body.goal_id, body.certificate_sha256, body.policy_sha256, authorize=lambda c: auth(request, c)
            )
        }

    @app.post("/v1/demo/decision")
    def decision(request: Request, body: DecisionBody) -> dict[str, bool]:
        auth(request)
        demo.decide(
            body.goal_id,
            body.approval_id,
            body.effect_digest,
            body.expected_version,
            body.decision,
            body.idempotency_key,
            authorize=lambda c: auth(request, c),
        )
        return {"recorded": True}

    @app.post("/v1/demo/cancel")
    def cancel(request: Request, body: CancelBody) -> dict[str, bool]:
        auth(request)
        demo.cancel(body.goal_id, body.expected_version, authorize=lambda c: auth(request, c))
        return {"recorded": True}

    return app
