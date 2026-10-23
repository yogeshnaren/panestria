"""Scoped challenges and immutable read-only phone session roles."""

from alembic import op

revision = "0040_phone_devices"
down_revision = "0039_curated_example_rights"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE panestria.browser_session ADD CONSTRAINT browser_session_scope_identity "
        "UNIQUE(id,owner_id,project_id)"
    )
    op.execute(
        "ALTER TABLE panestria.pairing_challenge ADD COLUMN scope_ref char(64) CHECK(scope_ref ~ '^[0-9a-f]{64}$')"
    )
    op.execute("""CREATE TABLE panestria.phone_device (
        session_id uuid PRIMARY KEY,
        owner_id uuid NOT NULL, project_id uuid NOT NULL,
        scope_ref char(64) NOT NULL CHECK(scope_ref ~ '^[0-9a-f]{64}$'),
        role text NOT NULL DEFAULT 'READ_ONLY_METADATA' CHECK(role='READ_ONLY_METADATA'),
        FOREIGN KEY(project_id,owner_id) REFERENCES panestria.project(id,owner_id),
        FOREIGN KEY(session_id,owner_id,project_id) REFERENCES panestria.browser_session(id,owner_id,project_id))""")
    op.execute("""CREATE FUNCTION panestria.guard_phone_device() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'phone role is immutable'; END $$""")
    op.execute(
        "CREATE TRIGGER phone_device_immutable BEFORE UPDATE OR DELETE ON panestria.phone_device "
        "FOR EACH ROW EXECUTE FUNCTION panestria.guard_phone_device()"
    )


def downgrade() -> None:
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM panestria.phone_device)
        OR EXISTS(SELECT 1 FROM panestria.pairing_challenge WHERE scope_ref IS NOT NULL)
        THEN RAISE EXCEPTION 'phone audit prevents downgrade'; END IF; END $$""")
    op.execute("DROP TABLE panestria.phone_device")
    op.execute("DROP FUNCTION panestria.guard_phone_device()")
    op.execute("ALTER TABLE panestria.pairing_challenge DROP COLUMN scope_ref")
    op.execute("ALTER TABLE panestria.browser_session DROP CONSTRAINT browser_session_scope_identity")
