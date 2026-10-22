"""Foreground read-only project observations: no model, grants or mutation routes."""

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


def build_activity_app(config: ActivitySettings, settings: ValidatedSettings, token: str) -> FastAPI:
    app = create_app(settings, default_readiness_probe)
    app.state.goal_api = GoalApi(
        token, str(config.owner_id), str(config.project_id), settings.database_url.get_secret_value()
    )
    mount_activity_api(app)
    return app


def serve_activity(
    path: Path,
    *,
    dashboard_assets: Path | None = None,
    build_evidence_store: Path | None = None,
    build_review_root: Path | None = None,
    research_intake: Path | None = None,
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
        app = build_activity_app(config, settings, token.get_secret_value())
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
            )
        server = uvicorn.Server(server_config(app))
        print(
            json.dumps(
                {
                    "status": "STARTING",
                    "origin": config.origin,
                    "authority": "PUBLIC_RESEARCH_STAGING_ONLY"
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
            app.state.health.shutdown()
