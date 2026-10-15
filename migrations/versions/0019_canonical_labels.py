"""Versioned canonical-label interfaces without rewriting immutable records."""

from alembic import op

revision = "0019_canonical_labels"
down_revision = "0018_memory_classification"
branch_labels = None
depends_on = None

_TABLES = ("memory_source", "context_pack", "learning_record", "user_correction")


def _constraint(table: str, *, canonical: bool) -> None:
    labels = "'PUBLIC','PRIVATE','RESTRICTED'"
    if canonical:
        labels += ",'INTERNAL','CONFIDENTIAL'"
    if table == "learning_record":
        labels += ",'UNKNOWN'"
    op.execute(
        f"ALTER TABLE panestria.{table} DROP CONSTRAINT {table}_privacy_label_check,"
        f" ADD CONSTRAINT {table}_privacy_label_check CHECK(privacy_label IN ({labels}))"
    )


def upgrade() -> None:
    for table in _TABLES:
        _constraint(table, canonical=True)


def downgrade() -> None:
    # Lock all affected tables before checking: no concurrent write can slip in.
    op.execute("LOCK TABLE " + ",".join(f"panestria.{table}" for table in _TABLES) + " IN ACCESS EXCLUSIVE MODE")
    for table in _TABLES:
        populated = op.get_bind().exec_driver_sql(
            f"SELECT EXISTS(SELECT 1 FROM panestria.{table} WHERE privacy_label IN ('INTERNAL','CONFIDENTIAL'))"
        ).scalar()
        if populated:
            raise RuntimeError("canonical classification data exists; use forward repair or a reviewed backup")
    for table in _TABLES:
        _constraint(table, canonical=False)
