"""Owner's explicit local read-only setup, independent of task execution."""

from alembic import op

revision = "0022_local_setup"
down_revision = "0021_profile_ask"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE panestria.local_project_setup (
        project_id uuid PRIMARY KEY, owner_id uuid NOT NULL,
        schema_version integer NOT NULL CHECK(schema_version=1),
        intent text NOT NULL CHECK(intent='OFFLINE_ASK'),
        policy_version bigint NOT NULL CHECK(policy_version=1),
        policy_sha256 char(64) NOT NULL CHECK(policy_sha256 ~ '^[0-9a-f]{64}$'),
        seq bigint NOT NULL UNIQUE DEFAULT
            nextval(pg_get_serial_sequence('panestria.task_event','seq')::regclass),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        FOREIGN KEY(project_id,owner_id) REFERENCES panestria.project(id,owner_id),
        FOREIGN KEY(project_id,policy_version) REFERENCES panestria.project_policy_revision(project_id,version))""")
    op.execute("""CREATE FUNCTION panestria.check_local_setup_policy() RETURNS trigger LANGUAGE plpgsql AS $fn$
        BEGIN
            IF NOT EXISTS(SELECT 1 FROM panestria.project_policy_revision r
                WHERE r.project_id=NEW.project_id AND r.owner_id=NEW.owner_id
                AND r.version=NEW.policy_version AND r.sha256=NEW.policy_sha256) THEN
                RAISE EXCEPTION 'local_setup_policy_mismatch';
            END IF;
            RETURN NEW;
        END; $fn$""")
    op.execute("""CREATE TRIGGER local_setup_policy BEFORE INSERT ON panestria.local_project_setup
        FOR EACH ROW EXECUTE FUNCTION panestria.check_local_setup_policy()""")
    op.execute("""CREATE TRIGGER immutable_local_setup BEFORE UPDATE OR DELETE ON panestria.local_project_setup
        FOR EACH ROW EXECUTE FUNCTION panestria.immutable_memory_record()""")


def downgrade() -> None:
    op.execute("LOCK TABLE panestria.local_project_setup IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().exec_driver_sql("SELECT EXISTS(SELECT 1 FROM panestria.local_project_setup)").scalar():
        raise RuntimeError("local setup audit exists; use forward repair or a reviewed backup")
    op.execute("DROP TABLE panestria.local_project_setup")
    op.execute("DROP FUNCTION panestria.check_local_setup_policy()")
