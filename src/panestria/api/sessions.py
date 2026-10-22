"""Browser authentication uses exact origin, private cookies and separate CSRF."""

from __future__ import annotations

import hashlib
from typing import Any, Literal
from urllib.parse import urlsplit

import psycopg
from fastapi import Request

from panestria.api.db import open_database
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.sessions import SessionService
from panestria.kernel.uow import UnitOfWork

COOKIE_NAME = "panestria_session"


class BrowserAccess:
    def __init__(
        self,
        origin: str,
        service: SessionService,
        database_url: str,
        *,
        namespace: Literal[
            "default",
            "mission",
            "mission-review",
            "mission-ask",
            "mission-research",
            "mission-build-intake",
            "mission-plan-review",
        ] = "default",
    ) -> None:
        parts = urlsplit(origin)
        if (
            parts.scheme not in {"http", "https"}
            or parts.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parts.port is None
            or parts.path
            or parts.query
            or parts.fragment
            or parts.username is not None
        ):
            raise ValueError("invalid_browser_origin")
        if namespace not in {
            "default",
            "mission",
            "mission-review",
            "mission-ask",
            "mission-research",
            "mission-build-intake",
            "mission-plan-review",
        }:
            raise ValueError("invalid_browser_namespace")
        self.cookie_name = (
            COOKIE_NAME
            if namespace == "default"
            else "panestria_" + namespace.replace("-", "_") + "_" + hashlib.sha256(origin.encode()).hexdigest()[:12]
        )
        self.origin = origin
        self.host = parts.netloc.lower()
        self.secure = parts.scheme == "https"
        self.service = service
        self.database_url = database_url

    def validate_origin(self, request: Request, *, mutation: bool) -> None:
        supplied = request.headers.get("origin")
        if supplied is not None and supplied != self.origin:
            raise KernelDenied("origin_denied")
        if mutation and supplied != self.origin:
            raise KernelDenied("origin_required")
        if request.headers.get("sec-fetch-site") not in {None, "same-origin", "none"}:
            raise KernelDenied("origin_denied")
        referrer = request.headers.get("referer")
        if referrer:
            parts = urlsplit(referrer)
            if f"{parts.scheme}://{parts.netloc}" != self.origin:
                raise KernelDenied("origin_denied")

    def authenticate(self, request: Request, actor: Actor, connection: psycopg.Connection[Any] | None = None) -> str:
        mutation = request.method not in {"GET", "HEAD", "OPTIONS"}
        self.validate_origin(request, mutation=mutation)
        token, csrf = request.cookies.get(self.cookie_name, ""), request.headers.get("x-panestria-csrf")
        if connection is not None:
            return self.service.authenticate(UnitOfWork(connection), actor, token, csrf=csrf, mutation=mutation)
        with open_database(self.database_url) as owned:
            return self.service.authenticate(UnitOfWork(owned), actor, token, csrf=csrf, mutation=mutation)
