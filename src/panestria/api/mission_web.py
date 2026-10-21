"""Explicit same-origin metadata dashboard; reuse activity and auth, no work routes."""

import hashlib
import hmac
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import Response

from panestria.api.main import mount_browser_api
from panestria.api.sessions import BrowserAccess
from panestria.config_activity import ActivitySettings
from panestria.config_local import LocalApplicationRejected
from panestria.kernel.sessions import SessionService


def mount_mission_control(app: FastAPI, config: ActivitySettings, token: str, directory: Path) -> None:
    # A deliberate, local production build; never run a dev server or fetch assets.
    try:
        if not directory.is_absolute() or directory.resolve() != directory or not directory.is_dir():
            raise LocalApplicationRejected("mission_build_required")
        assets = {}
        for name, maximum in (("index.html", 16384), ("mission.js", 1048576), ("mission.css", 65536)):
            path = directory / name
            if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
                raise LocalApplicationRejected("mission_build_required")
            data = path.read_bytes()
            if not data or len(data) > maximum:
                raise LocalApplicationRejected("mission_build_required")
            assets[name] = data
    except OSError:
        raise LocalApplicationRejected("mission_build_required") from None
    secret = hmac.digest(token.encode(), b"panestria.mission-session.v1\0" + config.origin.encode(), "sha256")
    mount_browser_api(
        app,
        BrowserAccess(config.origin, SessionService(secret), app.state.goal_api.database_url, namespace="mission"),
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
