"""Immutable release proofs preserve the original claim/handoff audit."""

from alembic import op

revision = "0035_build_claim_release"
down_revision = "0034_build_admission"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE panestria.build_claim_release (
        attempt_id uuid PRIMARY KEY REFERENCES panestria.build_worker_claim(attempt_id),
        reason text NOT NULL CHECK(reason IN ('NO_DISPATCH','VERIFIED_FINAL')),
        proof jsonb NOT NULL CHECK(jsonb_typeof(proof)='object' AND octet_length(proof::text)<=32768),
        proof_sha256 char(64) NOT NULL CHECK(proof_sha256 ~ '^[0-9a-f]{64}$'),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp())""")
    op.execute("""CREATE TRIGGER immutable_build_claim_release BEFORE UPDATE OR DELETE
        ON panestria.build_claim_release FOR EACH ROW EXECUTE FUNCTION panestria.immutable_memory_record()""")
    op.execute("""CREATE VIEW panestria.build_active_worker_claim AS SELECT c.*
        FROM panestria.build_worker_claim c WHERE c.released_at IS NULL AND NOT EXISTS
        (SELECT 1 FROM panestria.build_claim_release r WHERE r.attempt_id=c.attempt_id)""")


def downgrade() -> None:
    op.execute("LOCK TABLE panestria.build_claim_release IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().exec_driver_sql("SELECT EXISTS(SELECT 1 FROM panestria.build_claim_release)").scalar():
        raise RuntimeError("build release audit exists; restore or forward repair required")
    op.execute("DROP VIEW panestria.build_active_worker_claim")
    op.execute("DROP TABLE panestria.build_claim_release")
