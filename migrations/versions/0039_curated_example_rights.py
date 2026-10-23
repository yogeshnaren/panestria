"""Immutable independent owner example rights decisions and withdrawal facts."""

from alembic import op

revision = "0039_curated_example_rights"
down_revision = "0038_fetch_connection_grants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE panestria.curated_example_review (
        review_sha256 char(64) PRIMARY KEY CHECK(review_sha256 ~ '^[a-f0-9]{64}$'),
        owner_id uuid NOT NULL,project_id uuid NOT NULL,
        example_sha256 char(64) NOT NULL CHECK(example_sha256 ~ '^[a-f0-9]{64}$'),
        content_sha256 char(64) NOT NULL CHECK(content_sha256 ~ '^[a-f0-9]{64}$'),
        preview jsonb NOT NULL CHECK(jsonb_typeof(preview)='object'
            AND octet_length(preview::text) BETWEEN 1 AND 32768),
        eligibility text NOT NULL CHECK(eligibility IN ('ALLOWED','DENIED','UNKNOWN')),
        purpose_consent boolean NOT NULL,
        decided_by uuid NOT NULL REFERENCES panestria.principal(id),
        decided_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        expires_at timestamptz NOT NULL,
        seq bigint NOT NULL UNIQUE DEFAULT nextval(pg_get_serial_sequence('panestria.task_event','seq')::regclass),
        CHECK(decided_by=owner_id),
        CHECK(eligibility<>'ALLOWED' OR purpose_consent),
        CHECK(expires_at>decided_at AND expires_at<=decided_at+interval '30 days'),
        UNIQUE(review_sha256,owner_id,project_id,content_sha256),
        FOREIGN KEY(project_id,owner_id) REFERENCES panestria.project(id,owner_id))""")
    op.execute("""CREATE INDEX curated_example_current ON panestria.curated_example_review
        (owner_id,project_id,content_sha256,seq DESC)""")
    op.execute("""CREATE TABLE panestria.curated_example_withdrawal (
        owner_id uuid NOT NULL,project_id uuid NOT NULL,content_sha256 char(64) NOT NULL,
        review_sha256 char(64) NOT NULL,
        withdrawn_by uuid NOT NULL REFERENCES panestria.principal(id),
        withdrawn_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        seq bigint NOT NULL UNIQUE DEFAULT nextval(pg_get_serial_sequence('panestria.task_event','seq')::regclass),
        PRIMARY KEY(owner_id,project_id,content_sha256),CHECK(withdrawn_by=owner_id),
        FOREIGN KEY(review_sha256,owner_id,project_id,content_sha256)
            REFERENCES panestria.curated_example_review(review_sha256,owner_id,project_id,content_sha256))""")
    for name in ("curated_example_review", "curated_example_withdrawal"):
        op.execute(f"""CREATE TRIGGER immutable_{name} BEFORE UPDATE OR DELETE ON panestria.{name}
            FOR EACH ROW EXECUTE FUNCTION panestria.immutable_memory_record()""")


def downgrade() -> None:
    op.execute(
        "LOCK TABLE panestria.curated_example_review,panestria.curated_example_withdrawal IN ACCESS EXCLUSIVE MODE"
    )
    if op.get_bind().exec_driver_sql("SELECT EXISTS(SELECT 1 FROM panestria.curated_example_review)").scalar():
        raise RuntimeError("curated example rights audit exists; restore or forward repair required")
    op.execute("DROP TABLE panestria.curated_example_withdrawal,panestria.curated_example_review")
