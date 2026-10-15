"""Versioned route/exposure/outcome evidence and consented owner corrections."""

from alembic import op

revision = "0012_learning"
down_revision = "0011_ask"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE panestria.learning_record (
        id uuid PRIMARY KEY, owner_id uuid NOT NULL, project_id uuid NOT NULL,
        request_id uuid, goal_id uuid, task_id uuid, trace_id char(32) NOT NULL,
        schema_version integer NOT NULL CHECK(schema_version=1),
        kind text NOT NULL CHECK(kind IN ('route','exposure','outcome')),
        policy_ref text NOT NULL, privacy_label text NOT NULL
            CHECK(privacy_label IN ('PUBLIC','PRIVATE','RESTRICTED','UNKNOWN')),
        body jsonb NOT NULL, sha256 char(64) NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(), UNIQUE(id,owner_id,project_id),
        CHECK((goal_id IS NULL)=(task_id IS NULL)), CHECK(trace_id ~ '^[0-9a-f]{32}$'),
        FOREIGN KEY(project_id,owner_id) REFERENCES panestria.project(id,owner_id),
        FOREIGN KEY(request_id,owner_id,project_id) REFERENCES panestria.ask_request(id,owner_id,project_id),
        FOREIGN KEY(task_id,goal_id) REFERENCES panestria.task(id,goal_id),
        FOREIGN KEY(goal_id,project_id,owner_id) REFERENCES panestria.goal(id,project_id,owner_id))""")
    op.execute("""CREATE TABLE panestria.user_correction (
        id uuid PRIMARY KEY, owner_id uuid NOT NULL, project_id uuid NOT NULL, request_id uuid NOT NULL,
        version integer NOT NULL CHECK(version>0), output_sha256 char(64) NOT NULL,
        kind text NOT NULL CHECK(kind IN ('explicit_text','diff','rejection')),
        body text NOT NULL, body_sha256 char(64) NOT NULL CHECK(body_sha256 ~ '^[0-9a-f]{64}$'),
        privacy_label text NOT NULL CHECK(privacy_label IN ('PUBLIC','PRIVATE','RESTRICTED')),
        consent_ref uuid NOT NULL, consented_by uuid NOT NULL REFERENCES panestria.principal(id),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        UNIQUE(request_id,owner_id,project_id,version), CHECK(consented_by=owner_id),
        FOREIGN KEY(request_id,owner_id,project_id) REFERENCES panestria.ask_request(id,owner_id,project_id))""")
    for table in ("learning_record", "user_correction"):
        op.execute(
            f"CREATE TRIGGER immutable_learning BEFORE UPDATE OR DELETE ON panestria.{table}"
            " FOR EACH ROW EXECUTE FUNCTION panestria.immutable_memory_record()"
        )
    op.execute("CREATE INDEX ix_learning_scope ON panestria.learning_record(owner_id,project_id,request_id)")


def downgrade() -> None:
    op.execute("DROP TABLE panestria.user_correction,panestria.learning_record")
