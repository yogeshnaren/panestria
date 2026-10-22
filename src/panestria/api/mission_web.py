"""Explicit same-origin dashboard modes; reuse activity, auth and existing runtimes."""

import asyncio
import hashlib
import hmac
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import Response

from panestria.api.main import mount_browser_api
from panestria.api.sessions import BrowserAccess
from panestria.config_activity import ActivitySettings
from panestria.config_local import LocalApplicationRejected
from panestria.kernel.sessions import SessionService


def mount_mission_control(
    app: FastAPI,
    config: ActivitySettings,
    token: str,
    directory: Path,
    *,
    build_evidence_store: Path | None = None,
    build_review_root: Path | None = None,
    offline_ask: bool = False,
    research_intake: Path | None = None,
    build_intake: bool = False,
    build_plan_review: bool = False,
    build_run: Path | None = None,
) -> None:
    run_service = None
    if build_run is not None:
        from panestria.execution.mission_run import MissionRunService
        from panestria.kernel.goals import Actor

        if (
            offline_ask
            or research_intake is not None
            or build_review_root is not None
            or build_evidence_store is not None
            or build_intake
            or build_plan_review
        ):
            raise LocalApplicationRejected("mission_build_select_one_mode")
        run_service = MissionRunService(
            build_run, Actor(str(config.owner_id), str(config.project_id)), app.state.goal_api.database_url
        )
        build_plan_review = True
    build_intake = build_intake or build_plan_review
    if build_intake and (
        offline_ask or research_intake is not None or build_review_root is not None or build_evidence_store is not None
    ):
        raise LocalApplicationRejected("mission_build_select_one_mode")
    if research_intake is not None and (
        offline_ask or build_review_root is not None or build_evidence_store is not None
    ):
        raise LocalApplicationRejected("mission_research_select_one_mode")
    if offline_ask:
        from panestria.api.routes.ask import AskApi

        if (
            build_review_root is not None
            or build_evidence_store is not None
            or not isinstance(getattr(app.state, "ask_api", None), AskApi)
            or getattr(app.state, "profile_api", None) is not None
        ):
            raise LocalApplicationRejected("mission_ask_scope_unavailable")
    # A deliberate, local production build; never run a dev server or fetch assets.
    try:
        if not directory.is_absolute() or directory.resolve() != directory or not directory.is_dir():
            raise LocalApplicationRejected("mission_build_required")
        assets = {}
        for name, maximum in (("index.html", 16384), ("mission.js", 1048576), ("mission.css", 65536)):
            path = directory / name
            if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
                raise LocalApplicationRejected("mission_build_required")
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as stream:
                data = stream.read(maximum + 1)
            if not data or len(data) > maximum:
                raise LocalApplicationRejected("mission_build_required")
            assets[name] = data
    except OSError:
        raise LocalApplicationRejected("mission_build_required") from None
    if run_service is not None:
        build_review_root = run_service.settings.root
    if build_review_root is not None:
        from panestria.api.routes.mission_review import router
        from panestria.execution.build_review import BuildReviewService

        if build_evidence_store is not None:
            raise LocalApplicationRejected("mission_review_select_one_store")
        app.state.build_review = BuildReviewService(build_review_root)
        app.state.build_evidence_reader = app.state.build_review.evidence
        app.include_router(router)
    elif build_evidence_store is not None:
        from panestria.kernel.build import BuildEvidenceService, BuildEvidenceStore

        app.state.build_evidence_reader = BuildEvidenceService(BuildEvidenceStore(build_evidence_store, read_only=True))
    purpose = (
        b"panestria.mission-review-session.v1\0" if build_review_root is not None else b"panestria.mission-session.v1\0"
    )
    if offline_ask:
        purpose = b"panestria.mission-ask-session.v1\0"
    if research_intake is not None:
        from panestria.api.routes.research_intake import router as research_router
        from panestria.execution.research_intake import ResearchIntakeService
        from panestria.kernel.goals import Actor

        service = ResearchIntakeService(research_intake, Actor(str(config.owner_id), str(config.project_id)))
        app.state.research_intake = service
        app.include_router(research_router)
        purpose = b"panestria.mission-research-session.v1\0" + service.view.template_sha256.encode() + b"\0"
    app.state.mission_offline_ask = offline_ask
    if build_intake:
        from panestria.api.routes.build_intake import router as build_intake_router
        from panestria.execution.build_intake import BuildIntakeService

        app.state.build_intake = BuildIntakeService(allow_acceptance=build_plan_review)
        app.include_router(build_intake_router)
        purpose = (
            b"panestria.mission-plan-review-session.v1\0"
            if build_plan_review
            else b"panestria.mission-build-intake-session.v1\0"
        )
    if run_service is not None:
        from panestria.api.routes.mission_run import router as run_router

        app.state.mission_run = run_service
        app.include_router(run_router)
        active_service = run_service

        @asynccontextmanager
        async def run_lifecycle(_: FastAPI) -> AsyncIterator[None]:
            try:
                yield
            finally:
                await asyncio.to_thread(active_service.close)

        app.include_router(APIRouter(lifespan=run_lifecycle))
        purpose = b"panestria.mission-build-run-session.v1\0" + run_service.configuration.encode() + b"\0"
    secret = hmac.digest(token.encode(), purpose + config.origin.encode(), "sha256")
    mount_browser_api(
        app,
        BrowserAccess(
            config.origin,
            SessionService(secret),
            app.state.goal_api.database_url,
            namespace="mission-build-run"
            if run_service is not None
            else "mission-plan-review"
            if build_plan_review
            else "mission-build-intake"
            if build_intake
            else "mission-research"
            if research_intake is not None
            else "mission-ask"
            if offline_ask
            else ("mission-review" if build_review_root is not None else "mission"),
        ),
    )
    app.state.mission_build_sha256 = hashlib.sha256(b"".join(assets.values())).hexdigest()

    @app.get("/", include_in_schema=False)
    def index() -> Response:
        return Response(assets["index.html"], media_type="text/html")

    @app.get("/ui/mission.js", include_in_schema=False)
    def script() -> Response:
        return Response(assets["mission.js"], media_type="text/javascript")

    @app.get("/ui/mission.css", include_in_schema=False)
    def style() -> Response:
        return Response(assets["mission.css"], media_type="text/css")
