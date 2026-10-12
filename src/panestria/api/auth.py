"""Loopback bearer checks. A browser Origin is not a CLI call."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse

from panestria.kernel.goals import Actor

MAX_BODY_BYTES = 65536
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})


class LoopbackDenied(Exception):
    def __init__(self, code: str, status_code: int) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(code)


@dataclass(frozen=True)
class GoalApi:
    token: str
    owner_id: str
    project_id: str
    database_url: str

    def __post_init__(self) -> None:
        if len(self.token) < 16:
            raise ValueError("loopback token is too short")


def authorize(request: Request, api: GoalApi) -> Actor:
    host = request.headers.get("host", "").split(":", 1)[0].strip("[]")
    if host not in _LOOPBACK_HOSTS:
        raise LoopbackDenied("invalid_host", 403)
    if "origin" in request.headers:
        raise LoopbackDenied("origin_denied", 403)
    header = request.headers.get("authorization", "")
    supplied = header.removeprefix("Bearer ") if header.startswith("Bearer ") else ""
    if len(supplied) != len(api.token) or not hmac.compare_digest(supplied, api.token):
        raise LoopbackDenied("unauthorized", 401)
    return Actor(api.owner_id, api.project_id)


def error_body(code: str) -> dict[str, object]:
    """Stable denial shape. The correlation id is generated here and is not taken from the request."""
    return {
        "code": code,
        "correlation_id": str(uuid4()),
        "message": code,
        "retryable": code == "database_unavailable",
    }


async def read_capped_body(request: Request) -> bytes | JSONResponse:
    """Stop once the body exceeds the cap. The extra bytes are not retained."""
    total = 0
    parts: list[bytes] = []
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_BODY_BYTES:
            return JSONResponse(status_code=413, content=error_body("body_too_large"))
        parts.append(chunk)
    return b"".join(parts)
