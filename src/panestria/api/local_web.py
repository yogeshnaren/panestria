"""Fixed packaged local Ask assets; the canonical API owns every action."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response


def mount_local_web(app: FastAPI) -> None:
    assets = files("panestria.api").joinpath("assets")

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse(assets.joinpath("ask.html").read_text())

    @app.get("/ui/ask.js")
    def script() -> Response:
        return Response(assets.joinpath("ask.js").read_bytes(), media_type="text/javascript")

    @app.get("/ui/ask.css")
    def stylesheet() -> Response:
        return Response(assets.joinpath("ask.css").read_bytes(), media_type="text/css")


@dataclass(frozen=True)
class LocalWeb:
    """The packaged local Ask page."""

    def mount(self, app: FastAPI) -> None:
        mount_local_web(app)
