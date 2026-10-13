"""Exact, one-use owner review for memory reclassification."""

from alembic import op

revision = "0014_memory_review"
down_revision = "0013_event_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE panestria.memory_review (
        id uuid PRIMARY KEY, owner_id uuid NOT NULL, project_id uuid NOT NULL, item_id uuid NOT NULL,
        expected_version bigint NOT NULL, old_sha256 char(64) NOT NULL,
        old_label text NOT NULL, policy_ref text NOT NULL, proposed jsonb NOT NULL,
        effect_digest char(64) NOT NULL CHECK(effect_digest ~ '^[0-9a-f]{64}$'),
        state text NOT NULL DEFAULT 'PENDING' CHECK(state IN ('PENDING','APPROVED','DENIED','CONSUMED')),
        expires_at timestamptz NOT NULL DEFAULT clock_timestamp()+interval '10 minutes',
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(), decided_by uuid, decided_at timestamptz,
        UNIQUE(id,owner_id,project_id),
        FOREIGN KEY(item_id,owner_id,project_id) REFERENCES panestria.memory_item(id,owner_id,project_id),
        CHECK(decided_by IS NULL OR decided_by=owner_id))""")
    op.execute("""CREATE FUNCTION panestria.guard_memory_review() RETURNS trigger LANGUAGE plpgsql AS $fn$
        BEGIN
            IF TG_OP='DELETE' THEN RAISE EXCEPTION 'memory review is immutable'; END IF;
            IF (NEW.id,NEW.owner_id,NEW.project_id,NEW.item_id,NEW.expected_version,NEW.old_sha256,
                NEW.old_label,NEW.policy_ref,NEW.proposed,NEW.effect_digest,NEW.expires_at,NEW.created_at)
                IS DISTINCT FROM (OLD.id,OLD.owner_id,OLD.project_id,OLD.item_id,OLD.expected_version,
                OLD.old_sha256,OLD.old_label,OLD.policy_ref,OLD.proposed,OLD.effect_digest,OLD.expires_at,OLD.created_at)
                THEN RAISE EXCEPTION 'memory review identity is immutable'; END IF;
            IF NOT (NEW.state=OLD.state OR (OLD.state='PENDING' AND NEW.state IN ('APPROVED','DENIED'))
                OR (OLD.state='APPROVED' AND NEW.state='CONSUMED'))
                THEN RAISE EXCEPTION 'invalid memory review transition'; END IF;
            IF OLD.decided_by IS NOT NULL AND (NEW.decided_by,NEW.decided_at)
                IS DISTINCT FROM (OLD.decided_by,OLD.decided_at)
                THEN RAISE EXCEPTION 'memory decision is immutable'; END IF;
            RETURN NEW;
        END; $fn$""")
    op.execute(
        "CREATE TRIGGER memory_review_guard BEFORE UPDATE OR DELETE ON panestria.memory_review"
        " FOR EACH ROW EXECUTE FUNCTION panestria.guard_memory_review()"
    )
    op.execute(
        "ALTER TABLE panestria.memory_source ADD COLUMN review_id uuid, ADD CONSTRAINT memory_source_review_scope"
        " FOREIGN KEY(review_id,owner_id,project_id) REFERENCES panestria.memory_review(id,owner_id,project_id)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE panestria.memory_source DROP CONSTRAINT memory_source_review_scope, DROP COLUMN review_id")
    op.execute("DROP TABLE panestria.memory_review")
    op.execute("DROP FUNCTION panestria.guard_memory_review()")
