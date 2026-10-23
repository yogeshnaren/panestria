"""One-use pairing and revocation. Raw codes/tokens are never persisted or event payloads."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork


@dataclass(frozen=True)
class SessionTokens:
    session_id: str
    token: str = field(repr=False)
    csrf: str = field(repr=False)
    expires_at: datetime


class SessionService:
    def __init__(self, secret: bytes, *, pairing_bytes: int = 4, challenge_scope: str | None = None) -> None:
        if len(secret) < 32:
            raise ValueError("session_secret_too_short")
        if pairing_bytes not in {4, 16} or (
            challenge_scope is not None and re.fullmatch(r"[0-9a-f]{64}", challenge_scope) is None
        ):
            raise ValueError("invalid_session_scope")
        self._secret = secret
        self.pairing_bytes, self.challenge_scope = pairing_bytes, challenge_scope

    def _hash(self, kind: str, value: str) -> str:
        return hmac.new(self._secret, f"{kind}:{value}".encode(), hashlib.sha256).hexdigest()

    def issue_pairing_code(self, uow: UnitOfWork, actor: Actor, *, ttl_seconds: int = 120) -> str:
        if not 1 <= ttl_seconds <= 300:
            raise KernelDenied("invalid_pairing_ttl")
        known = uow.execute(
            "SELECT id FROM panestria.project WHERE id=%s AND owner_id=%s FOR UPDATE",
            (actor.project_id, actor.owner_id),
        ).fetchone()
        if known is None:
            raise KernelDenied("not_found")
        # Issuing a new code invalidates earlier outstanding codes for this project.
        uow.execute(
            "UPDATE panestria.pairing_challenge SET used_at=clock_timestamp()"
            " WHERE owner_id=%s AND project_id=%s AND used_at IS NULL AND scope_ref IS NOT DISTINCT FROM %s",
            (actor.owner_id, actor.project_id, self.challenge_scope),
        )
        code = secrets.token_hex(self.pairing_bytes).upper()
        uow.execute(
            "INSERT INTO panestria.pairing_challenge(code_hash,owner_id,project_id,expires_at,scope_ref)"
            " VALUES (%s,%s,%s,clock_timestamp()+make_interval(secs => %s),%s)",
            (self._hash("pair", code), actor.owner_id, actor.project_id, ttl_seconds, self.challenge_scope),
        )
        return code

    def pair(self, uow: UnitOfWork, actor: Actor, code: str, *, session_seconds: int = 8 * 3600) -> SessionTokens:
        if (
            not 1 <= session_seconds <= 8 * 3600
            or re.fullmatch(r"[0-9A-F]{%d}" % (self.pairing_bytes * 2), code) is None
        ):
            raise KernelDenied("invalid_pairing_code")
        row = uow.execute(
            "SELECT used_at IS NULL AND expires_at>clock_timestamp()"
            " FROM panestria.pairing_challenge WHERE code_hash=%s AND owner_id=%s AND project_id=%s"
            " AND scope_ref IS NOT DISTINCT FROM %s FOR UPDATE",
            (self._hash("pair", code), actor.owner_id, actor.project_id, self.challenge_scope),
        ).fetchone()
        if row is None or row[0] is not True:
            raise KernelDenied("invalid_pairing_code")
        uow.execute(
            "UPDATE panestria.pairing_challenge SET used_at=clock_timestamp() WHERE code_hash=%s",
            (self._hash("pair", code),),
        )
        token, csrf, session_id = secrets.token_urlsafe(32), secrets.token_urlsafe(32), str(uuid4())
        expiry = uow.execute(
            "INSERT INTO panestria.browser_session"
            " (id,token_hash,csrf_hash,owner_id,project_id,expires_at)"
            " VALUES (%s,%s,%s,%s,%s,clock_timestamp()+make_interval(secs => %s)) RETURNING expires_at",
            (
                session_id,
                self._hash("session", token),
                self._hash("csrf", csrf),
                actor.owner_id,
                actor.project_id,
                session_seconds,
            ),
        ).fetchone()
        assert expiry is not None
        return SessionTokens(session_id, token, csrf, expiry[0])

    def authenticate(
        self, uow: UnitOfWork, actor: Actor, token: str, *, csrf: str | None = None, mutation: bool = False
    ) -> str:
        if len(token) > 128 or len(token) < 32:
            raise KernelDenied("unauthorized")
        row = uow.execute(
            "SELECT id::text,csrf_hash FROM panestria.browser_session"
            " WHERE token_hash=%s AND owner_id=%s AND project_id=%s"
            " AND revoked_at IS NULL AND expires_at>clock_timestamp() FOR SHARE",
            (self._hash("session", token), actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("unauthorized")
        if mutation and (
            csrf is None or len(csrf) > 128 or not hmac.compare_digest(self._hash("csrf", csrf), str(row[1]))
        ):
            raise KernelDenied("csrf_denied")
        return str(row[0])

    def revoke(self, uow: UnitOfWork, actor: Actor, token: str, csrf: str) -> None:
        # Take an exclusive lock directly: concurrent logout must not upgrade two shared locks.
        row = uow.execute(
            "SELECT id::text,csrf_hash FROM panestria.browser_session"
            " WHERE token_hash=%s AND owner_id=%s AND project_id=%s"
            " AND revoked_at IS NULL AND expires_at>clock_timestamp() FOR UPDATE",
            (self._hash("session", token), actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("unauthorized")
        if len(csrf) > 128 or not hmac.compare_digest(self._hash("csrf", csrf), str(row[1])):
            raise KernelDenied("csrf_denied")
        uow.execute("UPDATE panestria.browser_session SET revoked_at=clock_timestamp() WHERE id=%s", (row[0],))
