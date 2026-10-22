"""A bounded scoped read-only snapshot of canonical pending plans and approvals."""

from datetime import datetime
from uuid import UUID

from panestria.contracts.review_inbox import ReviewInbox, ReviewInboxEntry
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork


def review_inbox(uow: UnitOfWork, actor: Actor, *, after: str | None = None, limit: int = 16) -> ReviewInbox:
    if type(limit) is not int or not 1 <= limit <= 32:
        raise KernelDenied("invalid_inbox_limit")
    if uow.execute(
        "SELECT current_setting('transaction_read_only'),current_setting('transaction_isolation')"
    ).fetchone() != ("on", "repeatable read"):
        raise KernelDenied("read_only_observation_required")
    if (
        uow.execute(
            "SELECT 1 FROM panestria.project WHERE id=%s AND owner_id=%s", (actor.project_id, actor.owner_id)
        ).fetchone()
        is None
    ):
        raise KernelDenied("not_found")
    anchor: tuple[datetime | None, str | None, str | None] = (None, None, None)
    if after is not None:
        try:
            kind, value = after.split(":")
            if kind not in {"PLAN", "APPROVAL"} or str(UUID(value)) != value:
                raise ValueError
        except (ValueError, AttributeError):
            raise KernelDenied("invalid_inbox_cursor") from None
        table = "build_plan" if kind == "PLAN" else "approval_request"
        row = uow.execute(
            f"SELECT expires_at FROM panestria.{table} WHERE id=%s AND owner_id=%s AND project_id=%s",
            (value, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        # Retained rows remain valid anchors even after the review is resolved.
        anchor = (row[0], value, kind)
    observed = uow.execute("SELECT clock_timestamp()").fetchone()
    assert observed is not None
    rows = uow.execute(
        """WITH pending AS (
          SELECT p.id,p.goal_id,NULL::uuid AS task_id,'PLAN'::text AS kind,
            'PROPOSED'::text AS state,g.status,p.expires_at
          FROM panestria.build_plan p JOIN panestria.goal g ON g.id=p.goal_id
          WHERE p.owner_id=%s AND p.project_id=%s AND g.status IN ('CREATED','ACTIVE')
            AND NOT EXISTS(SELECT 1 FROM panestria.build_plan_acceptance a WHERE a.plan_id=p.id)
            AND NOT EXISTS(SELECT 1 FROM panestria.build_plan newer
              WHERE newer.goal_id=p.goal_id AND newer.version>p.version)
          UNION ALL
          SELECT a.id,a.goal_id,a.task_id,'APPROVAL'::text,a.state,g.status,a.expires_at
          FROM panestria.approval_request a JOIN panestria.goal g ON g.id=a.goal_id
          WHERE a.owner_id=%s AND a.project_id=%s AND a.state='PENDING' AND g.status IN ('CREATED','ACTIVE')
        ) SELECT * FROM pending WHERE (%s::timestamptz IS NULL
            OR (expires_at,id,kind)>(%s::timestamptz,%s::uuid,%s::text))
          ORDER BY expires_at,id,kind LIMIT %s""",
        (actor.owner_id, actor.project_id, actor.owner_id, actor.project_id, anchor[0], *anchor, limit + 1),
    ).fetchall()
    entries = tuple(
        ReviewInboxEntry(
            id=r[0],
            goal_id=r[1],
            task_id=r[2],
            kind=r[3],
            canonical_state=r[4],
            goal_status=r[5],
            expires_at=r[6],
            expired=r[6] <= observed[0],
        )
        for r in rows[:limit]
    )
    return ReviewInbox(
        owner_id=UUID(actor.owner_id),
        project_id=UUID(actor.project_id),
        observed_at=observed[0],
        entries=entries,
        next_cursor=f"{entries[-1].kind}:{entries[-1].id}" if len(rows) > limit else None,
    )
