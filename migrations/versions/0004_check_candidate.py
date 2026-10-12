"""Bind each check run to the candidate it judged."""

from __future__ import annotations

from alembic import op

revision = "0004_check_candidate"
down_revision = "0003_approval_preview"
branch_labels = None
depends_on = None

_UPGRADE = (
    "ALTER TABLE panestria.check_run ADD COLUMN candidate_sha256 char(64)",
    "ALTER TABLE panestria.check_run ADD CONSTRAINT check_run_candidate_hex"
    " CHECK (candidate_sha256 IS NULL OR candidate_sha256 ~ '^[0-9a-f]{64}$')",
    "ALTER TABLE panestria.check_run ADD CONSTRAINT check_run_pass_has_candidate"
    " CHECK (verdict <> 'PASS' OR candidate_sha256 IS NOT NULL)",
)

_DOWNGRADE = (
    "ALTER TABLE panestria.check_run DROP CONSTRAINT IF EXISTS check_run_pass_has_candidate",
    "ALTER TABLE panestria.check_run DROP CONSTRAINT IF EXISTS check_run_candidate_hex",
    "ALTER TABLE panestria.check_run DROP COLUMN IF EXISTS candidate_sha256",
)


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
