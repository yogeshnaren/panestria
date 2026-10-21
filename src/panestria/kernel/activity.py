"""One scoped snapshot of Ask requests and canonical goals; no content or I/O dispatch."""

from datetime import datetime
from uuid import UUID

from panestria.contracts.activity import ActivityEntry, ProjectActivity
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork


def project_activity(uow: UnitOfWork, actor: Actor, *, before: str | None = None, limit: int = 16) -> ProjectActivity:
    if type(limit) is not int or not 1 <= limit <= 32:
        raise KernelDenied("invalid_activity_limit")
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
    if before is not None:
        try:
            kind, value = before.split(":")
            if kind not in {"ASK", "GOAL"} or str(UUID(value)) != value:
                raise ValueError
        except (ValueError, AttributeError):
            raise KernelDenied("invalid_activity_cursor") from None
        table = "ask_request" if kind == "ASK" else "goal"  # Fixed whitelist, never worker-selected SQL.
        found = uow.execute(
            f"SELECT created_at FROM panestria.{table} WHERE id=%s AND owner_id=%s AND project_id=%s",
            (value, actor.owner_id, actor.project_id),
        ).fetchone()
        if found is None:
            raise KernelDenied("not_found")
        anchor = (found[0], value, kind)
    observed = uow.execute("SELECT clock_timestamp()").fetchone()
    assert observed is not None
    rows = uow.execute(
        """WITH entries AS (
          SELECT a.id,a.created_at,'ASK'::text AS source,'ASK'::text AS workflow,a.state,
            CASE WHEN a.state IN ('PREPARED','RUNNING') THEN 1 ELSE 0 END AS active,
            0::bigint AS reviews, NULL::bigint AS held,
            (a.state='UNAVAILABLE' OR (a.state IN ('PREPARED','RUNNING')
             AND a.deadline_at<=clock_timestamp())) AS attention
          FROM panestria.ask_request a WHERE a.owner_id=%s AND a.project_id=%s
          UNION ALL
          SELECT g.id,g.created_at,'GOAL'::text,
            CASE WHEN EXISTS(SELECT 1 FROM panestria.research_request r WHERE r.goal_id=g.id) THEN 'DELEGATE'
              WHEN EXISTS(SELECT 1 FROM panestria.build_plan p WHERE p.goal_id=g.id)
                OR EXISTS(SELECT 1 FROM panestria.task t WHERE t.goal_id=g.id
                          AND t.name='Owner PUBLIC native Build') THEN 'BUILD' ELSE 'KERNEL' END,
            g.status,
            (SELECT count(*) FROM panestria.task t WHERE t.goal_id=g.id
              AND t.state IN ('LEASED','RUNNING','VERIFYING')),
            (SELECT count(*) FROM panestria.task t WHERE t.goal_id=g.id AND t.state='WAITING_APPROVAL'),
            (SELECT count(*) FROM panestria.build_active_worker_claim c
             JOIN panestria.task t ON t.id=c.task_id WHERE t.goal_id=g.id),
            (g.status='FAILED' OR EXISTS(SELECT 1 FROM panestria.task t WHERE t.goal_id=g.id
              AND t.state IN ('WAITING_APPROVAL','RECONCILING','CANCELLING','FAILED','RETRY_WAIT'))
             OR EXISTS(SELECT 1 FROM panestria.build_active_worker_claim c
                JOIN panestria.task t ON t.id=c.task_id JOIN panestria.task_attempt a ON a.id=c.attempt_id
                WHERE t.goal_id=g.id AND (a.lease_expires_at<=clock_timestamp()
                OR EXISTS(SELECT 1 FROM panestria.worker_invocation i WHERE i.attempt_id=c.attempt_id
                          AND i.state='UNKNOWN'))))
          FROM panestria.goal g WHERE g.owner_id=%s AND g.project_id=%s
        ) SELECT * FROM entries WHERE (%s::timestamptz IS NULL
            OR (created_at,id,source)<(%s::timestamptz,%s::uuid,%s::text))
          ORDER BY created_at DESC,id DESC,source DESC LIMIT %s""",
        (actor.owner_id, actor.project_id, actor.owner_id, actor.project_id, anchor[0], *anchor, limit + 1),
    ).fetchall()
    entries = tuple(
        ActivityEntry(
            id=r[0],
            created_at=r[1],
            source=r[2],
            workflow=r[3],
            canonical_state=r[4],
            active_tasks=r[5],
            waiting_reviews=r[6],
            held_build_claims=r[7] if r[3] == "BUILD" else None,
            needs_attention=r[8],
        )
        for r in rows[:limit]
    )
    return ProjectActivity(
        owner_id=UUID(actor.owner_id),
        project_id=UUID(actor.project_id),
        observed_at=observed[0],
        entries=entries,
        next_cursor=f"{entries[-1].source}:{entries[-1].id}" if len(rows) > limit else None,
    )
