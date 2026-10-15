"""Hash-only one-use pairing challenges and revocable scoped browser sessions."""

from alembic import op

revision = "0009_browser_sessions"
down_revision = "0008_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE panestria.pairing_challenge (
        code_hash char(64) PRIMARY KEY CHECK(code_hash ~ '^[0-9a-f]{64}$'),
        owner_id uuid NOT NULL, project_id uuid NOT NULL,
        expires_at timestamptz NOT NULL, used_at timestamptz,
        FOREIGN KEY(project_id,owner_id) REFERENCES panestria.project(id,owner_id))""")
    op.execute("""CREATE TABLE panestria.browser_session (
        id uuid PRIMARY KEY, token_hash char(64) NOT NULL UNIQUE CHECK(token_hash ~ '^[0-9a-f]{64}$'),
        csrf_hash char(64) NOT NULL CHECK(csrf_hash ~ '^[0-9a-f]{64}$'),
        owner_id uuid NOT NULL, project_id uuid NOT NULL,
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        expires_at timestamptz NOT NULL, revoked_at timestamptz,
        FOREIGN KEY(project_id,owner_id) REFERENCES panestria.project(id,owner_id))""")


def downgrade() -> None:
    op.execute("DROP TABLE panestria.browser_session,panestria.pairing_challenge")
