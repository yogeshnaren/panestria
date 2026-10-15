"""One-use external invocation claims on the application's existing database."""

from alembic import op

revision = "0017_worker_invocation"
down_revision = "0016_approval_revocation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE panestria.worker_invocation (
        id uuid PRIMARY KEY, task_id uuid NOT NULL, attempt_id uuid NOT NULL,
        invocation_key varchar(128) NOT NULL, binding jsonb NOT NULL,
        binding_sha256 char(64) NOT NULL CHECK(binding_sha256 ~ '^[0-9a-f]{64}$'),
        state text NOT NULL DEFAULT 'PREPARED' CHECK(state IN ('PREPARED','CLAIMED','RETURNED','UNKNOWN')),
        receipt_sha256 char(64) CHECK(receipt_sha256 ~ '^[0-9a-f]{64}$'),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(), expires_at timestamptz NOT NULL,
        finished_at timestamptz,
        UNIQUE(attempt_id,invocation_key),
        FOREIGN KEY(attempt_id,task_id) REFERENCES panestria.task_attempt(id,task_id),
        CHECK(jsonb_typeof(binding)='object'), CHECK(expires_at>created_at),
        CHECK((state IN ('RETURNED','UNKNOWN'))=(finished_at IS NOT NULL)),
        CHECK((state='RETURNED')=(receipt_sha256 IS NOT NULL)))""")
    op.execute("""CREATE FUNCTION panestria.guard_worker_invocation() RETURNS trigger LANGUAGE plpgsql AS $fn$
        BEGIN
            IF TG_OP='DELETE' THEN RAISE EXCEPTION 'invocation history is immutable'; END IF;
            IF (NEW.id,NEW.task_id,NEW.attempt_id,NEW.invocation_key,NEW.binding,NEW.binding_sha256,
                NEW.created_at,NEW.expires_at) IS DISTINCT FROM
               (OLD.id,OLD.task_id,OLD.attempt_id,OLD.invocation_key,OLD.binding,OLD.binding_sha256,
                OLD.created_at,OLD.expires_at) THEN RAISE EXCEPTION 'invocation binding is immutable'; END IF;
            IF NOT ((OLD.state='PREPARED' AND NEW.state='CLAIMED') OR
                    (OLD.state='CLAIMED' AND NEW.state IN ('RETURNED','UNKNOWN'))) THEN
                RAISE EXCEPTION 'invocation cannot be replayed'; END IF;
            RETURN NEW;
        END; $fn$""")
    op.execute("""CREATE TRIGGER worker_invocation_immutable BEFORE UPDATE OR DELETE ON panestria.worker_invocation
        FOR EACH ROW EXECUTE FUNCTION panestria.guard_worker_invocation()""")


def downgrade() -> None:
    op.execute("DROP TABLE panestria.worker_invocation")
    op.execute("DROP FUNCTION panestria.guard_worker_invocation()")
