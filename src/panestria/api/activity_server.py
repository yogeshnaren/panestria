"""Foreground project server; explicitly selected modes retain distinct authority."""

import json
import os
import resource
import socket
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from panestria.api.auth import GoalApi
from panestria.api.health import default_readiness_probe
from panestria.api.local_server import server_config
from panestria.api.main import create_app, mount_activity_api
from panestria.config import Settings, ValidatedSettings
from panestria.config_activity import ActivitySettings, load_activity_settings
from panestria.config_local import LocalApplicationRejected


def build_activity_app(
    config: ActivitySettings,
    settings: ValidatedSettings,
    token: str,
    *,
    storage_config: Path | None = None,
    connection_reviews: bool = False,
) -> FastAPI:
    if connection_reviews and storage_config is not None:
        raise LocalApplicationRejected("connection_terminal_mode_only")
    app = create_app(settings, default_readiness_probe)
    app.state.goal_api = GoalApi(
        token, str(config.owner_id), str(config.project_id), settings.database_url.get_secret_value()
    )
    if storage_config is not None:
        from collections.abc import AsyncIterator
        from contextlib import asynccontextmanager

        from fastapi import APIRouter

        from panestria.kernel.goals import Actor
        from panestria.resources.storage_status import StorageObserver

        observer = StorageObserver(Actor(str(config.owner_id), str(config.project_id)), storage_config)
        app.state.storage_observer = observer

        @asynccontextmanager
        async def storage_lifecycle(_: FastAPI) -> AsyncIterator[None]:
            try:
                yield
            finally:
                observer.close()

        app.include_router(APIRouter(lifespan=storage_lifecycle))
    mount_activity_api(app)
    if connection_reviews:
        from panestria.api.routes.connections import router as connection_router

        app.state.connection_terminal_only = True
        app.include_router(connection_router)
    return app


def serve_activity(
    path: Path,
    *,
    dashboard_assets: Path | None = None,
    build_evidence_store: Path | None = None,
    build_review_root: Path | None = None,
    research_intake: Path | None = None,
    build_intake: bool = False,
    build_plan_review: bool = False,
    build_run: Path | None = None,
    storage_config: Path | None = None,
    connection_reviews: bool = False,
) -> None:
    config, token = load_activity_settings(path)
    settings = Settings(
        database_url=os.environ.get("PANESTRIA_DATABASE_URL", ""), bind_host="127.0.0.1", bind_port=config.bind_port
    ).validate_profile()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    app = None
    try:
        # Exclusive port reservation; never kill or reuse an existing owner's listener.
        try:
            listener.bind(("127.0.0.1", config.bind_port))
            listener.listen(16)
            listener.setblocking(False)
        except OSError:
            raise LocalApplicationRejected("local_bind_unavailable") from None
        if connection_reviews and any(
            (
                dashboard_assets,
                build_evidence_store,
                build_review_root,
                research_intake,
                build_intake,
                build_plan_review,
                build_run,
                storage_config,
            )
        ):
            raise LocalApplicationRejected("connection_terminal_mode_only")
        if storage_config is not None and dashboard_assets is not None:
            # Browser/phone host-data consent needs its own namespace integration.
            raise LocalApplicationRejected("storage_terminal_mode_only")
        if connection_reviews:
            app = build_activity_app(config, settings, token.get_secret_value(), connection_reviews=True)
        elif storage_config is None:
            app = build_activity_app(config, settings, token.get_secret_value())
        else:
            app = build_activity_app(config, settings, token.get_secret_value(), storage_config=storage_config)
        if dashboard_assets is not None:
            from panestria.api.mission_web import mount_mission_control

            mount_mission_control(
                app,
                config,
                token.get_secret_value(),
                dashboard_assets,
                build_evidence_store=build_evidence_store,
                build_review_root=build_review_root,
                research_intake=research_intake,
                build_intake=build_intake,
                build_plan_review=build_plan_review,
                build_run=build_run,
            )
        server = uvicorn.Server(server_config(app))
        print(
            json.dumps(
                {
                    "status": "STARTING",
                    "origin": config.origin,
                    "authority": "CONNECTION_DECLARATION_REVIEW_ONLY"
                    if connection_reviews
                    else "EXPLICIT_FOREGROUND_BUILD"
                    if build_run is not None
                    else "PUBLIC_PLAN_ACCEPTANCE_ONLY"
                    if build_plan_review
                    else "PUBLIC_BUILD_PLAN_STAGING_ONLY"
                    if build_intake
                    else "PUBLIC_RESEARCH_STAGING_ONLY"
                    if research_intake
                    else "PUBLIC_BUILD_REVIEW_CONSENT_ONLY"
                    if build_review_root
                    else "READ_ONLY_METADATA",
                }
            ),
            flush=True,
        )
        try:
            server.run(sockets=[listener])
        except SystemExit:
            raise LocalApplicationRejected("activity_startup_failed") from None
        if not server.started:
            raise LocalApplicationRejected("activity_startup_failed")
    finally:
        listener.close()
        if app is not None:
            observer = getattr(app.state, "storage_observer", None)
            if observer is not None:
                observer.close()
            app.state.health.shutdown()
