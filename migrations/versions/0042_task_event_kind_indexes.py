"""Index task_event by kind for background queue, run and withdrawal lookups."""

from alembic import op

revision = "0042_task_event_kind_indexes"
down_revision = "0041_memory_restricted_fts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX ix_task_event_kind_goal ON panestria.task_event(kind,goal_id,seq)")
    op.execute("CREATE INDEX ix_task_event_task_kind ON panestria.task_event(task_id,kind,seq)")


def downgrade() -> None:
    op.execute("DROP INDEX panestria.ix_task_event_task_kind")
    op.execute("DROP INDEX panestria.ix_task_event_kind_goal")
