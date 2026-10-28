"""Phone role binding supplements canonical browser sessions, never task authority."""

from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.sessions import SessionService, SessionTokens
from panestria.kernel.uow import UnitOfWork


class PhoneSessionService(SessionService):
    def __init__(self, secret: bytes, scope_ref: str) -> None:
        super().__init__(secret, pairing_bytes=16, challenge_scope=scope_ref)

    def pair(self, uow: UnitOfWork, actor: Actor, code: str, *, session_seconds: int = 3600) -> SessionTokens:
        if not 1 <= session_seconds <= 3600:
            raise KernelDenied("invalid_phone_session_ttl")
        # Serialize role admission within the project. Device history is retained,
        # never pruned; only live (unrevoked, unexpired) devices count toward the
        # cap, so revoked or expired history cannot lock out new pairings.
        row = uow.execute(
            "SELECT id FROM panestria.project WHERE id=%s AND owner_id=%s FOR UPDATE",
            (actor.project_id, actor.owner_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        count = uow.execute(
            "SELECT count(*) FROM panestria.phone_device p JOIN panestria.browser_session s ON s.id=p.session_id "
            "WHERE p.owner_id=%s AND p.project_id=%s AND s.revoked_at IS NULL AND s.expires_at>clock_timestamp()",
            (actor.owner_id, actor.project_id),
        ).fetchone()
        if count is None or count[0] >= 256:
            raise KernelDenied("phone_device_history_limit")  # Wire code kept; now counts live devices.
        tokens = super().pair(uow, actor, code, session_seconds=session_seconds)
        uow.execute(
            "INSERT INTO panestria.phone_device(session_id,owner_id,project_id,scope_ref) VALUES (%s,%s,%s,%s)",
            (tokens.session_id, actor.owner_id, actor.project_id, self.challenge_scope),
        )
        return tokens

    def authenticate(
        self, uow: UnitOfWork, actor: Actor, token: str, *, csrf: str | None = None, mutation: bool = False
    ) -> str:
        identity = super().authenticate(uow, actor, token, csrf=csrf, mutation=mutation)
        row = uow.execute(
            "SELECT session_id FROM panestria.phone_device WHERE session_id=%s AND owner_id=%s "
            "AND project_id=%s AND scope_ref=%s AND role='READ_ONLY_METADATA'",
            (identity, actor.owner_id, actor.project_id, self.challenge_scope),
        ).fetchone()
        if row is None:
            raise KernelDenied("unauthorized")
        return identity

    def devices(self, uow: UnitOfWork, actor: Actor) -> list[dict[str, object]]:
        rows = uow.execute(
            "SELECT s.id::text,s.created_at,s.expires_at,s.revoked_at,p.scope_ref,"
            "CASE WHEN s.revoked_at IS NOT NULL THEN 'REVOKED' WHEN s.expires_at<=clock_timestamp() "
            "THEN 'EXPIRED' ELSE 'ACTIVE' END FROM panestria.phone_device p "
            "JOIN panestria.browser_session s ON s.id=p.session_id WHERE p.owner_id=%s AND p.project_id=%s "
            "ORDER BY s.created_at DESC,s.id DESC LIMIT 256",
            (actor.owner_id, actor.project_id),
        ).fetchall()
        return [
            dict(
                session_id=r[0],
                created_at=r[1].isoformat(),
                expires_at=r[2].isoformat(),
                revoked_at=r[3].isoformat() if r[3] else None,
                role="READ_ONLY_METADATA",
                scope_ref=str(r[4]).strip(),
                current_profile=str(r[4]).strip() == self.challenge_scope,
                state=r[5],
            )
            for r in rows
        ]

    def revoke_device(self, uow: UnitOfWork, actor: Actor, identity: str) -> None:
        row = uow.execute(
            "SELECT s.id FROM panestria.phone_device p JOIN panestria.browser_session s ON s.id=p.session_id "
            "WHERE p.session_id=%s AND p.owner_id=%s AND p.project_id=%s FOR UPDATE OF s",
            (identity, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        uow.execute(
            "UPDATE panestria.browser_session SET revoked_at=COALESCE(revoked_at,clock_timestamp()) WHERE id=%s",
            (identity,),
        )
