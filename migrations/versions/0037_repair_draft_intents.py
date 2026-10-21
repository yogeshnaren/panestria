"""Bound durable repair I/O admission and immutable outcomes in the event ledger."""

from alembic import op

revision = "0037_repair_draft_intents"
down_revision = "0036_returned_build_release"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE panestria.task_event ADD CONSTRAINT repair_draft_start_shape CHECK(
        kind!='build.repair_draft.started' OR COALESCE((
        task_id IS NULL AND jsonb_typeof(payload)='object'
        AND payload->>'turn' IN ('1','2') AND payload->>'maximum_turns' IN ('1','2')
        AND jsonb_typeof(payload->'turn')='number' AND jsonb_typeof(payload->'maximum_turns')='number'
        AND (payload->>'turn')<=(payload->>'maximum_turns')
        AND payload->>'reserved_wall_seconds'='360' AND jsonb_typeof(payload->'reserved_wall_seconds')='number'
        AND payload->>'return_proof_sha256' ~ '^[0-9a-f]{64}$'
        AND payload->>'key_sha256' ~ '^[0-9a-f]{64}$'
        AND payload->>'directory_sha256' ~ '^[0-9a-f]{64}$'
        AND payload->>'context_sha256' ~ '^[0-9a-f]{64}$'
        AND payload->>'request_sha256' ~ '^[0-9a-f]{64}$'
        AND payload->>'contract_sha256' ~ '^[0-9a-f]{64}$'
        AND payload->>'parent_sha256' ~ '^[0-9a-f]{64}$'
        AND payload->>'draft_id' ~ '^[0-9a-f-]{36}$'
        AND payload->>'parent_plan_id' ~ '^[0-9a-f-]{36}$'),false))""")
    op.execute("""ALTER TABLE panestria.task_event ADD CONSTRAINT repair_draft_finish_shape CHECK(
        kind!='build.repair_draft.finished' OR COALESCE((
        task_id IS NULL AND jsonb_typeof(payload)='object'
        AND payload->>'draft_id' ~ '^[0-9a-f-]{36}$'
        AND payload->>'intent_sha256' ~ '^[0-9a-f]{64}$'
        AND payload->>'status' IN ('RETAINED','NOT_PUBLISHED','UNCONFIRMED')
        AND payload->>'physical_return' IN ('CONFIRMED','UNCONFIRMED')
        AND jsonb_typeof(payload->'files')='object'),false))""")
    op.execute("""CREATE UNIQUE INDEX repair_draft_turn_once ON panestria.task_event
        (goal_id,(payload->>'turn')) WHERE kind='build.repair_draft.started'""")
    op.execute("""CREATE UNIQUE INDEX repair_draft_key_once ON panestria.task_event
        (goal_id,(payload->>'key_sha256')) WHERE kind='build.repair_draft.started'""")
    op.execute("""CREATE UNIQUE INDEX repair_draft_outcome_once ON panestria.task_event
        (goal_id,(payload->>'draft_id')) WHERE kind='build.repair_draft.finished'""")


def downgrade() -> None:
    op.execute("LOCK TABLE panestria.task_event IN ACCESS EXCLUSIVE MODE")
    if (
        op.get_bind()
        .exec_driver_sql(
            "SELECT EXISTS(SELECT 1 FROM panestria.task_event WHERE kind IN "
            "('build.repair_draft.started','build.repair_draft.finished'))"
        )
        .scalar()
    ):
        raise RuntimeError("repair I/O audit exists; restore or forward repair required")
    for name in ("repair_draft_turn_once", "repair_draft_key_once", "repair_draft_outcome_once"):
        op.execute(f"DROP INDEX panestria.{name}")
    op.execute("ALTER TABLE panestria.task_event DROP CONSTRAINT repair_draft_start_shape")
    op.execute("ALTER TABLE panestria.task_event DROP CONSTRAINT repair_draft_finish_shape")
