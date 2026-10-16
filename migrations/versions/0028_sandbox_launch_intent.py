"""Immutable launch reference on the existing PostgreSQL invocation ledger."""

from alembic import op

revision = "0028_sandbox_launch_intent"
down_revision = "0027_connection_reviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE panestria.worker_invocation ADD CONSTRAINT worker_invocation_launch_binding "
        "UNIQUE(id,binding_sha256)"
    )
    op.execute("""CREATE TABLE panestria.worker_invocation_launch (
        invocation_id uuid PRIMARY KEY,
        binding_sha256 char(64) NOT NULL CHECK(binding_sha256 ~ '^[0-9a-f]{64}$'),
        launch_id uuid NOT NULL UNIQUE CHECK(substring(launch_id::text,15,1)='4'
            AND substring(launch_id::text,20,1) IN ('8','9','a','b')),
        runtime_attempt_id uuid NOT NULL UNIQUE,
        body jsonb NOT NULL, body_sha256 char(64) NOT NULL CHECK(body_sha256 ~ '^[0-9a-f]{64}$'),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        FOREIGN KEY(invocation_id,binding_sha256) REFERENCES panestria.worker_invocation(id,binding_sha256),
        CHECK(jsonb_typeof(body)='object'),
        CHECK(body ?& ARRAY['schema_version','invocation_id','binding_sha256','scope_sha256',
            'runtime_attempt_id','launch_id','profile_sha256','image_id']),
        CHECK(body - ARRAY['schema_version','invocation_id','binding_sha256','scope_sha256',
            'runtime_attempt_id','launch_id','profile_sha256','image_id'] = '{}'::jsonb),
        CHECK(body->>'schema_version'='1' AND jsonb_typeof(body->'schema_version')='number'),
        CHECK(body->>'invocation_id'=invocation_id::text AND jsonb_typeof(body->'invocation_id')='string'),
        CHECK(body->>'binding_sha256'=binding_sha256::text AND jsonb_typeof(body->'binding_sha256')='string'),
        CHECK(body->>'launch_id'=launch_id::text AND jsonb_typeof(body->'launch_id')='string'),
        CHECK(body->>'runtime_attempt_id'=runtime_attempt_id::text
            AND jsonb_typeof(body->'runtime_attempt_id')='string'),
        CHECK(jsonb_typeof(body->'scope_sha256')='string' AND body->>'scope_sha256' ~ '^[0-9a-f]{64}$'),
        CHECK(jsonb_typeof(body->'profile_sha256')='string' AND body->>'profile_sha256' ~ '^[0-9a-f]{64}$'),
        CHECK(jsonb_typeof(body->'image_id')='string' AND body->>'image_id' ~ '^sha256:[0-9a-f]{64}$'))""")
    op.execute("""CREATE FUNCTION panestria.guard_sandbox_launch_insert() RETURNS trigger LANGUAGE plpgsql AS $fn$
        BEGIN
            PERFORM 1 FROM panestria.worker_invocation WHERE id=NEW.invocation_id
                AND binding_sha256=NEW.binding_sha256 AND state='CLAIMED' AND expires_at>clock_timestamp()
                AND binding->>'kind'='native-tool' FOR UPDATE;
            IF NOT FOUND THEN RAISE EXCEPTION 'sandbox launch invocation is not active'; END IF;
            RETURN NEW;
        END; $fn$""")
    op.execute("""CREATE TRIGGER sandbox_launch_insert BEFORE INSERT ON panestria.worker_invocation_launch
        FOR EACH ROW EXECUTE FUNCTION panestria.guard_sandbox_launch_insert()""")
    op.execute("""CREATE FUNCTION panestria.immutable_sandbox_launch() RETURNS trigger LANGUAGE plpgsql AS $fn$
        BEGIN RAISE EXCEPTION 'sandbox launch history is immutable'; END; $fn$""")
    op.execute("""CREATE TRIGGER sandbox_launch_immutable BEFORE UPDATE OR DELETE ON panestria.worker_invocation_launch
        FOR EACH ROW EXECUTE FUNCTION panestria.immutable_sandbox_launch()""")


def downgrade() -> None:
    op.execute("LOCK TABLE panestria.worker_invocation_launch IN SHARE ROW EXCLUSIVE MODE")
    if op.get_bind().exec_driver_sql("SELECT EXISTS(SELECT 1 FROM panestria.worker_invocation_launch)").scalar():
        raise RuntimeError("sandbox launch audit exists; use forward repair or a reviewed backup")
    op.execute("DROP TABLE panestria.worker_invocation_launch")
    op.execute("DROP FUNCTION panestria.immutable_sandbox_launch()")
    op.execute("DROP FUNCTION panestria.guard_sandbox_launch_insert()")
    op.execute("ALTER TABLE panestria.worker_invocation DROP CONSTRAINT worker_invocation_launch_binding")
