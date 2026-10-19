"""Allow separately explicit structured-style profile renderer; retain all v1 audit bytes."""

from alembic import op

revision = "0032_structured_style"
down_revision = "0031_fetch_admission"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE panestria.ask_profile_context DROP CONSTRAINT ask_profile_context_render_version_check")
    op.execute(
        "ALTER TABLE panestria.ask_profile_context ADD CONSTRAINT "
        "ask_profile_context_render_version_check CHECK(render_version IN (1,2))"
    )


def downgrade() -> None:
    op.execute("""DO $fn$ BEGIN
        IF EXISTS(SELECT 1 FROM panestria.ask_profile_context WHERE render_version=2) THEN
            RAISE EXCEPTION 'structured style audit exists; restore or forward repair required';
        END IF; END $fn$""")
    op.execute("ALTER TABLE panestria.ask_profile_context DROP CONSTRAINT ask_profile_context_render_version_check")
    op.execute(
        "ALTER TABLE panestria.ask_profile_context ADD CONSTRAINT "
        "ask_profile_context_render_version_check CHECK(render_version=1)"
    )
