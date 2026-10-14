"""Forward-only, immutable evidence for an exact leased Build candidate."""

from alembic import op

revision = "0015_build_evidence"
down_revision = "0014_memory_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE panestria.build_evidence (
        id uuid PRIMARY KEY, task_id uuid NOT NULL, attempt_id uuid NOT NULL,
        contract_id uuid NOT NULL, artifact_id uuid NOT NULL UNIQUE,
        sha256 char(64) NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'), body jsonb NOT NULL,
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        UNIQUE(task_id,sha256),
        FOREIGN KEY(task_id,contract_id) REFERENCES panestria.task(id,contract_id),
        FOREIGN KEY(attempt_id,task_id) REFERENCES panestria.task_attempt(id,task_id),
        FOREIGN KEY(artifact_id,task_id) REFERENCES panestria.artifact(id,task_id),
        CHECK(jsonb_typeof(body)='object'))""")
    op.execute("""CREATE FUNCTION panestria.immutable_build_evidence() RETURNS trigger LANGUAGE plpgsql AS $fn$
        BEGIN RAISE EXCEPTION 'build evidence is immutable'; END; $fn$""")
    op.execute(
        "CREATE TRIGGER build_evidence_immutable BEFORE UPDATE OR DELETE ON panestria.build_evidence"
        " FOR EACH ROW EXECUTE FUNCTION panestria.immutable_build_evidence()"
    )
    op.execute(
        "CREATE TRIGGER build_evidence_lease BEFORE INSERT ON panestria.build_evidence"
        " FOR EACH ROW EXECUTE FUNCTION panestria.fence_leased_publication()"
    )


def downgrade() -> None:
    op.execute("DROP TABLE panestria.build_evidence")
    op.execute("DROP FUNCTION panestria.immutable_build_evidence()")
