"""Browser authentication uses exact origin, private cookies and separate CSRF.

A single-mode server has one ``BrowserAccess`` (``app.state.browser_access``).
The owner app has a ``BrowserScopes``: one ``BrowserAccess`` per session scope
(activity, Ask, Build) on the same origin, each with its own cookie, session
key and pairing codes. Each route accepts a fixed set of scopes, set by the
``AcceptScopes`` dependency it is mounted with, and ``selected_access`` picks
the session that request may use. A session paired for one scope cannot be
used for another: its token is hashed with its own scope's key, so another
scope's key finds no session.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Iterator
from typing import Any, Literal, get_args
from urllib.parse import urlsplit

import psycopg
from fastapi import Request

from panestria.api.db import open_database
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.sessions import SessionService
from panestria.kernel.uow import UnitOfWork

COOKIE_NAME = "panestria_session"
BrowserNamespace = Literal[
    "default",
    "mission",
    "mission-review",
    "mission-ask",
    "mission-research",
    "mission-build-intake",
    "mission-plan-review",
    "mission-build-run",
    "mission-storage",
    "mission-phone",
    "owner-activity",
    "owner-ask",
    "owner-build",
]
# Release 1 owner app scopes. Activity is content-free observation; Ask covers
# questions and memory; Build covers review, plan acceptance and runs.
SessionScope = Literal["activity", "ask", "build"]
SESSION_SCOPES: tuple[SessionScope, ...] = get_args(SessionScope)


class BrowserAccess:
    def __init__(
        self,
        origin: str,
        service: SessionService,
        database_url: str,
        *,
        namespace: BrowserNamespace = "default",
    ) -> None:
        parts = urlsplit(origin)
        if (
            parts.scheme not in {"http", "https"}
            or not self._origin_host_allowed(parts.hostname, parts.scheme)
            or (parts.port is None and not (self.private_read_only and parts.scheme == "https"))
            or parts.path
            or parts.query
            or parts.fragment
            or parts.username is not None
        ):
            raise ValueError("invalid_browser_origin")
        if namespace not in get_args(BrowserNamespace):
            raise ValueError("invalid_browser_namespace")
        self.cookie_name = (
            COOKIE_NAME
            if namespace == "default"
            else "panestria_" + namespace.replace("-", "_") + "_" + hashlib.sha256(origin.encode()).hexdigest()[:12]
        )
        self.origin = origin
        self.namespace = namespace
        self.host = parts.netloc.lower()
        self.secure = parts.scheme == "https"
        self.service = service
        self.database_url = database_url
        self.session_seconds = 8 * 3600

    @staticmethod
    def _origin_host_allowed(host: str | None, scheme: str) -> bool:
        return host in {"127.0.0.1", "localhost", "::1"}

    @property
    def private_read_only(self) -> bool:
        return False

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


class BrowserScopes:
    """One browser session per scope on one origin, each with its own cookie, key and pairing codes."""

    def __init__(self, origin: str, token: str, database_url: str) -> None:
        self._scopes: dict[SessionScope, BrowserAccess] = {}
        for scope in SESSION_SCOPES:
            purpose = b"panestria.owner-session.v1\0" + scope.encode() + b"\0" + origin.encode()
            # A code issued for one scope never invalidates another scope's outstanding code.
            challenge = hashlib.sha256(b"panestria.owner-pairing.v1\0" + scope.encode()).hexdigest()
            access = BrowserAccess(
                origin,
                SessionService(hmac.digest(token.encode(), purpose, "sha256"), challenge_scope=challenge),
                database_url,
                namespace=_OWNER_NAMESPACES[scope],
            )
            access.session_seconds = SESSION_SECONDS[scope]
            self._scopes[scope] = access
        self.origin, self.database_url = origin, database_url

    def __getitem__(self, scope: SessionScope) -> BrowserAccess:
        return self._scopes[scope]

    def __iter__(self) -> Iterator[BrowserAccess]:
        return iter(self._scopes.values())


# A Build session can read diffs, approve and start runs, so it lasts an hour;
# re-pairing takes one CLI code. Observation and Ask sessions last a working day.
SESSION_SECONDS: dict[SessionScope, int] = {"activity": 8 * 3600, "ask": 8 * 3600, "build": 3600}

_OWNER_NAMESPACES: dict[SessionScope, BrowserNamespace] = {
    "activity": "owner-activity",
    "ask": "owner-ask",
    "build": "owner-build",
}


class AcceptScopes:
    """Route dependency: the session scopes this route accepts on an app with ``BrowserScopes``."""

    def __init__(self, *scopes: SessionScope) -> None:
        if not scopes or any(scope not in SESSION_SCOPES for scope in scopes):
            raise ValueError("invalid_session_scope")
        self.scopes = scopes

    def __call__(self, request: Request) -> None:
        owner = getattr(request.app.state, "browser_scopes", None)
        # Without scopes configured, accept none: cookies are ignored, fail closed.
        request.state.accepted_scopes = tuple(owner[s] for s in self.scopes) if isinstance(owner, BrowserScopes) else ()


def browser_wired(request: Request) -> bool:
    """Whether the app serves browsers at all: any browser access or session scopes, of any kind."""
    state = request.app.state
    return getattr(state, "browser_access", None) is not None or getattr(state, "browser_scopes", None) is not None


def selected_access(request: Request) -> BrowserAccess | None:
    """The browser session this request may use, if any."""
    accepted: tuple[BrowserAccess, ...] | None = getattr(request.state, "accepted_scopes", None)
    if accepted is None:
        if isinstance(getattr(request.app.state, "browser_scopes", None), BrowserScopes):
            return None  # A route mounted without a scope accepts no browser session.
        access = getattr(request.app.state, "browser_access", None)
        return access if isinstance(access, BrowserAccess) else None
    for access in accepted:
        if request.cookies.get(access.cookie_name):
            return access
    return accepted[0] if accepted else None


def holds_other_scope(request: Request) -> bool:
    """Whether the request carries a session cookie only for scopes this route does not accept."""
    owner = getattr(request.app.state, "browser_scopes", None)
    if not isinstance(owner, BrowserScopes):
        return False
    accepted = getattr(request.state, "accepted_scopes", ())
    return any(access not in accepted and request.cookies.get(access.cookie_name) for access in owner)
