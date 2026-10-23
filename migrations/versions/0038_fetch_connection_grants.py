"""Immutable grant-version bindings and conservative per-dispatch connection capacity."""

from alembic import op

revision = "0038_fetch_connection_grants"
down_revision = "0037_repair_draft_intents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing rows stay unbound historical records; no fabricated grant/backfill.
    op.execute("""ALTER TABLE panestria.fetch_plan
        ADD COLUMN connection_grant_id uuid,
        ADD COLUMN connection_grant_version integer,
        ADD CONSTRAINT fetch_connection_shape CHECK(
            (connection_grant_id IS NULL AND connection_grant_version IS NULL) OR
            (connection_grant_id IS NOT NULL AND connection_grant_version IS NOT NULL
                AND connection_grant_version BETWEEN 1 AND 1000001)),
        ADD CONSTRAINT fetch_connection_revision FOREIGN KEY(connection_grant_id,connection_grant_version)
            REFERENCES panestria.connection_grant_revision(grant_id,version),
        ADD CONSTRAINT fetch_connection_identity UNIQUE(task_id,request_id,connection_grant_id,connection_grant_version)
    """)
    op.execute("""CREATE INDEX fetch_connection_budget ON panestria.fetch_plan
        (connection_grant_id,connection_grant_version) WHERE connection_grant_id IS NOT NULL""")
    op.execute("""CREATE TABLE panestria.connection_fetch_reservation (
        dispatch_id uuid PRIMARY KEY,
        task_id uuid NOT NULL,request_id uuid NOT NULL,
        grant_id uuid NOT NULL,grant_version integer NOT NULL,
        reserved_hops integer NOT NULL CHECK(reserved_hops BETWEEN 1 AND 6),
        reserved_bytes bigint NOT NULL CHECK(reserved_bytes BETWEEN 49155 AND 67108864),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        FOREIGN KEY(dispatch_id,task_id,request_id) REFERENCES panestria.fetch_dispatch(id,task_id,request_id),
        FOREIGN KEY(task_id,request_id,grant_id,grant_version) REFERENCES panestria.fetch_plan
            (task_id,request_id,connection_grant_id,connection_grant_version))""")
    op.execute("""CREATE FUNCTION panestria.fetch_connection_capacity_consistent()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE body_bytes integer; redirect_limit integer;
        BEGIN
            SELECT d.reserved_body_bytes,r.max_redirects INTO body_bytes,redirect_limit
                FROM panestria.fetch_dispatch d JOIN panestria.research_request r ON r.id=d.request_id
                WHERE d.id=NEW.dispatch_id;
            IF body_bytes IS NULL OR NEW.reserved_bytes != body_bytes+NEW.reserved_hops*49153
                OR NEW.reserved_hops>redirect_limit+1 THEN
                RAISE EXCEPTION 'fetch connection capacity mismatch';
            END IF;
            RETURN NEW;
        END; $$""")
    op.execute("""CREATE CONSTRAINT TRIGGER fetch_connection_capacity_consistent
        AFTER INSERT ON panestria.connection_fetch_reservation DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION panestria.fetch_connection_capacity_consistent()""")
    op.execute("""CREATE TRIGGER immutable_connection_fetch_reservation BEFORE UPDATE OR DELETE
        ON panestria.connection_fetch_reservation FOR EACH ROW EXECUTE FUNCTION panestria.immutable_memory_record()""")


def downgrade() -> None:
    op.execute("LOCK TABLE panestria.fetch_plan,panestria.connection_fetch_reservation IN ACCESS EXCLUSIVE MODE")
    if (
        op.get_bind()
        .exec_driver_sql("""SELECT EXISTS(SELECT 1 FROM panestria.connection_fetch_reservation)
        OR EXISTS(SELECT 1 FROM panestria.fetch_plan WHERE connection_grant_id IS NOT NULL)""")
        .scalar()
    ):
        raise RuntimeError("fetch admission audit exists (connection grants); restore or forward repair required")
    op.execute("DROP TABLE panestria.connection_fetch_reservation")
    op.execute("DROP FUNCTION panestria.fetch_connection_capacity_consistent()")
    op.execute("DROP INDEX panestria.fetch_connection_budget")
    op.execute("""ALTER TABLE panestria.fetch_plan DROP CONSTRAINT fetch_connection_identity,
        DROP CONSTRAINT fetch_connection_revision,DROP CONSTRAINT fetch_connection_shape,
        DROP COLUMN connection_grant_id,DROP COLUMN connection_grant_version""")
