"""One bounded canonical query, scoped to the configured owner and project."""

from datetime import UTC
from uuid import UUID

from panestria.contracts.build_index import BuildGoalIndex, BuildGoalSummary
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork


def build_goal_index(uow: UnitOfWork, actor: Actor) -> BuildGoalIndex:
    rows = uow.execute(
        """SELECT g.id,left(g.intent,120),g.status,g.created_at,
          (EXISTS(SELECT 1 FROM panestria.build_plan p WHERE p.goal_id=g.id AND p.state='ACCEPTED')
           OR EXISTS(SELECT 1 FROM panestria.task t WHERE t.goal_id=g.id AND t.name='Owner PUBLIC native Build')),
          (SELECT count(*) FROM panestria.task t WHERE t.goal_id=g.id AND t.state IN ('RUNNING','VERIFYING')),
          (SELECT count(*) FROM panestria.task t WHERE t.goal_id=g.id AND t.state='WAITING_APPROVAL')
        FROM panestria.goal g
        JOIN LATERAL (SELECT c.body FROM panestria.goal_contract c
                      WHERE c.goal_id=g.id ORDER BY c.version DESC LIMIT 1) c ON true
        WHERE g.owner_id=%s AND g.project_id=%s AND c.body->>'privacy_class'='PUBLIC'
          AND (EXISTS(SELECT 1 FROM panestria.build_plan p WHERE p.goal_id=g.id)
               OR EXISTS(SELECT 1 FROM panestria.task t WHERE t.goal_id=g.id AND t.name='Owner PUBLIC native Build'))
        ORDER BY g.created_at DESC,g.id LIMIT 32""",
        (actor.owner_id, actor.project_id),
    ).fetchall()
    return BuildGoalIndex(
        owner_id=UUID(actor.owner_id),
        project_id=UUID(actor.project_id),
        goals=tuple(
            BuildGoalSummary(
                goal_id=r[0],
                title=r[1][:120],
                status=r[2],
                created_at=r[3].astimezone(UTC).isoformat(),
                review_available=r[4],
                running_tasks=r[5],
                waiting_reviews=r[6],
            )
            for r in rows
        ),
    )
