"""Immutable retained-source capture proof, separate from generic snapshot metadata."""

from alembic import op

revision = "0025_source_capture"
down_revision = "0024_source_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE panestria.research_source_snapshot ADD CONSTRAINT source_snapshot_pinned_body "
        "UNIQUE(id,task_id,body_sha256)"
    )
    op.execute("""CREATE TABLE panestria.research_source_capture (
        snapshot_id uuid PRIMARY KEY, task_id uuid NOT NULL, metadata_sha256 char(64) NOT NULL,
        proof_artifact_id uuid NOT NULL, proof_sha256 char(64) NOT NULL CHECK(proof_sha256 ~ '^[0-9a-f]{64}$'),
        proof_size_bytes bigint NOT NULL CHECK(proof_size_bytes BETWEEN 1 AND 32768),
        privacy_class text NOT NULL CHECK(privacy_class IN ('PUBLIC','INTERNAL','CONFIDENTIAL','RESTRICTED')),
        seq bigint NOT NULL UNIQUE DEFAULT nextval(pg_get_serial_sequence('panestria.task_event','seq')::regclass),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        FOREIGN KEY(snapshot_id,task_id,metadata_sha256)
            REFERENCES panestria.research_source_snapshot(id,task_id,body_sha256),
        FOREIGN KEY(proof_artifact_id,task_id,proof_sha256,proof_size_bytes,privacy_class)
            REFERENCES panestria.artifact(id,task_id,sha256,size_bytes,privacy_class))""")
    op.execute(
        "CREATE TRIGGER immutable_research_source_capture BEFORE UPDATE OR DELETE "
        "ON panestria.research_source_capture FOR EACH ROW EXECUTE FUNCTION panestria.immutable_memory_record()"
    )


def downgrade() -> None:
    op.execute("LOCK TABLE panestria.research_source_capture IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().exec_driver_sql("SELECT EXISTS(SELECT 1 FROM panestria.research_source_capture)").scalar():
        raise RuntimeError("source capture audit exists; use forward repair or a reviewed backup")
    op.execute("DROP TABLE panestria.research_source_capture")
    op.execute("ALTER TABLE panestria.research_source_snapshot DROP CONSTRAINT source_snapshot_pinned_body")
