"""Offline request identity/receipts without retaining question or response text."""

from alembic import op

revision = "0011_ask"
down_revision = "0010_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE panestria.ask_request (
        id uuid NOT NULL, owner_id uuid NOT NULL, project_id uuid NOT NULL,
        request_sha256 char(64) NOT NULL CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
        context_pack_id uuid NOT NULL, model_ref text NOT NULL, policy_ref text NOT NULL,
        trace_id char(32) NOT NULL CHECK(trace_id ~ '^[0-9a-f]{32}$'),
        state text NOT NULL DEFAULT 'PREPARED' CHECK(state IN (
            'PREPARED','RUNNING','COMPLETED','UNAVAILABLE','CANCELLED')),
        deadline_at timestamptz NOT NULL, response_sha256 char(64), metadata jsonb, code text,
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        PRIMARY KEY(id,owner_id,project_id),
        FOREIGN KEY(project_id,owner_id) REFERENCES panestria.project(id,owner_id),
        FOREIGN KEY(context_pack_id,owner_id,project_id) REFERENCES panestria.context_pack(id,owner_id,project_id),
        CHECK((state='COMPLETED')=(response_sha256 IS NOT NULL)),
        CHECK(response_sha256 IS NULL OR response_sha256 ~ '^[0-9a-f]{64}$'))""")
    op.execute("""CREATE FUNCTION panestria.guard_ask_request() RETURNS trigger LANGUAGE plpgsql AS $fn$
        BEGIN
            IF (NEW.id,NEW.owner_id,NEW.project_id,NEW.request_sha256,NEW.context_pack_id,NEW.model_ref,
                NEW.policy_ref,NEW.trace_id,NEW.deadline_at,NEW.created_at)
                IS DISTINCT FROM (OLD.id,OLD.owner_id,OLD.project_id,OLD.request_sha256,OLD.context_pack_id,
                OLD.model_ref,OLD.policy_ref,OLD.trace_id,OLD.deadline_at,OLD.created_at)
                THEN RAISE EXCEPTION 'ask request identity is immutable'; END IF;
            IF OLD.state IN ('COMPLETED','UNAVAILABLE','CANCELLED') AND NEW IS DISTINCT FROM OLD
                THEN RAISE EXCEPTION 'terminal ask receipt is immutable'; END IF;
            RETURN NEW;
        END; $fn$""")
    op.execute(
        "CREATE TRIGGER ask_identity_guard BEFORE UPDATE ON panestria.ask_request"
        " FOR EACH ROW EXECUTE FUNCTION panestria.guard_ask_request()"
    )


def downgrade() -> None:
    op.execute("DROP TABLE panestria.ask_request")
    op.execute("DROP FUNCTION panestria.guard_ask_request()")
