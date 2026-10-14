"""Empty application schema. Domain tables belong to later revisions."""

from __future__ import annotations

from alembic import op

revision = "0001_scaffold"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS panestria")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS panestria")
