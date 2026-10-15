"""Immutable research request scope and question artifact metadata; no fetch authority."""

from alembic import op

revision = "0023_research_request"
down_revision = "0022_local_setup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE panestria.artifact ADD CONSTRAINT artifact_pinned_metadata "
        "UNIQUE(id,task_id,sha256,size_bytes,privacy_class)"
    )
    op.execute("""CREATE TABLE panestria.research_request (
        id uuid PRIMARY KEY, schema_version integer NOT NULL CHECK(schema_version=1),
        owner_id uuid NOT NULL, project_id uuid NOT NULL, goal_id uuid NOT NULL, task_id uuid NOT NULL,
        question_artifact_id uuid NOT NULL, question_sha256 char(64) NOT NULL,
        question_size_bytes bigint NOT NULL CHECK(question_size_bytes BETWEEN 0 AND 2097152),
        privacy_class text NOT NULL CHECK(privacy_class IN ('PUBLIC','INTERNAL','CONFIDENTIAL','RESTRICTED')),
        max_sources integer NOT NULL CHECK(max_sources BETWEEN 1 AND 16),
        max_source_bytes integer NOT NULL CHECK(max_source_bytes BETWEEN 1 AND 2097152),
        max_total_bytes integer NOT NULL CHECK(max_total_bytes BETWEEN max_source_bytes AND 33554432),
        max_redirects integer NOT NULL CHECK(max_redirects BETWEEN 0 AND 5),
        deadline_seconds double precision NOT NULL CHECK(deadline_seconds BETWEEN 1 AND 300),
        request_sha256 char(64) NOT NULL CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
        seq bigint NOT NULL UNIQUE DEFAULT nextval(pg_get_serial_sequence('panestria.task_event','seq')::regclass),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        UNIQUE(id,task_id),
        FOREIGN KEY(goal_id,project_id,owner_id) REFERENCES panestria.goal(id,project_id,owner_id),
        FOREIGN KEY(task_id,goal_id) REFERENCES panestria.task(id,goal_id),
        FOREIGN KEY(question_artifact_id,task_id,question_sha256,question_size_bytes,privacy_class)
            REFERENCES panestria.artifact(id,task_id,sha256,size_bytes,privacy_class))""")
    op.execute("""CREATE TRIGGER immutable_research_request BEFORE UPDATE OR DELETE ON panestria.research_request
        FOR EACH ROW EXECUTE FUNCTION panestria.immutable_memory_record()""")


def downgrade() -> None:
    op.execute("LOCK TABLE panestria.research_request IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().exec_driver_sql("SELECT EXISTS(SELECT 1 FROM panestria.research_request)").scalar():
        raise RuntimeError("research request audit exists; use forward repair or a reviewed backup")
    op.execute("DROP TABLE panestria.research_request")
    op.execute("ALTER TABLE panestria.artifact DROP CONSTRAINT artifact_pinned_metadata")
