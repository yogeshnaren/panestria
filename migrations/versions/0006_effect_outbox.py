"""Transactional dispatch intents; ambiguous effects require reconciliation."""

from alembic import op

revision = "0006_effect_outbox"
down_revision = "0005_leases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE panestria.side_effect ADD COLUMN classification text"
        " CHECK (classification IN ('read-only','idempotent-with-key','reconcile-by-query',"
        "'compensatable','non-retryable'))"
    )
    op.execute(
        "ALTER TABLE panestria.side_effect ADD COLUMN request_ref text,"
        " ADD COLUMN dispatch_epoch bigint NOT NULL DEFAULT 0,"
        " ADD COLUMN dispatch_attempts integer NOT NULL DEFAULT 0,"
        " ADD CONSTRAINT side_effect_id_task_unique UNIQUE(id,task_id)"
    )
    op.execute("""CREATE TABLE panestria.effect_outbox (
        effect_id uuid PRIMARY KEY,
        task_id uuid NOT NULL,
        state text NOT NULL CHECK(state IN ('PENDING','CLAIMED','DONE','PAUSED')),
        due_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        claim_expires_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        FOREIGN KEY(effect_id,task_id) REFERENCES panestria.side_effect(id,task_id))""")
    op.execute("CREATE INDEX ix_outbox_due ON panestria.effect_outbox(due_at) WHERE state='PENDING'")


def downgrade() -> None:
    op.execute("DROP TABLE panestria.effect_outbox")
    op.execute(
        "ALTER TABLE panestria.side_effect DROP CONSTRAINT side_effect_id_task_unique,"
        " DROP COLUMN classification, DROP COLUMN request_ref, DROP COLUMN dispatch_epoch,"
        " DROP COLUMN dispatch_attempts"
    )
