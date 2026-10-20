"""Allow immutable physically confirmed historical Build return proofs."""

from alembic import op

revision = "0036_returned_build_release"
down_revision = "0035_build_claim_release"
branch_labels = None
depends_on = None


def _constraint(reasons: str) -> None:
    op.drop_constraint("build_claim_release_reason_check", "build_claim_release", schema="panestria", type_="check")
    op.create_check_constraint(
        "build_claim_release_reason_check", "build_claim_release", "reason IN (" + reasons + ")", schema="panestria"
    )


def upgrade() -> None:
    _constraint("'NO_DISPATCH','VERIFIED_FINAL','VERIFIED_RETURN'")


def downgrade() -> None:
    op.execute("LOCK TABLE panestria.build_claim_release IN ACCESS EXCLUSIVE MODE")
    if (
        op.get_bind()
        .exec_driver_sql("SELECT EXISTS(SELECT 1 FROM panestria.build_claim_release WHERE reason='VERIFIED_RETURN')")
        .scalar()
    ):
        raise RuntimeError("returned Build release audit exists; restore or forward repair required")
    _constraint("'NO_DISPATCH','VERIFIED_FINAL'")
