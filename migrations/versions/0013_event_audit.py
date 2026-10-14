"""Immutable event digests and explicit logical replay-retention floors."""

from alembic import op

revision = "0013_event_audit"
down_revision = "0012_learning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE panestria.task_event ADD COLUMN schema_version integer NOT NULL DEFAULT 1 CHECK(schema_version=1),"
        " ADD COLUMN privacy_label text NOT NULL DEFAULT 'UNKNOWN'"
        " CHECK(privacy_label IN ('PUBLIC','PRIVATE','RESTRICTED','UNKNOWN'))"
    )
    op.execute("""CREATE FUNCTION panestria.event_digest(
        event_id uuid, goal uuid, task uuid, attempt uuid, cursor bigint, event_kind text,
        event_actor text, trace text, event_body jsonb, version integer, label text)
        RETURNS text LANGUAGE sql IMMUTABLE AS $fn$
        SELECT encode(sha256(convert_to(jsonb_build_object(
            'id',event_id,'goal_id',goal,'task_id',task,'attempt_id',attempt,'seq',cursor,
            'kind',event_kind,'actor',event_actor,'trace_id',trace,'payload',event_body,
            'schema_version',version,'privacy_label',label)::text,'UTF8')),'hex')
        $fn$""")
    op.execute(
        "ALTER TABLE panestria.task_event ADD COLUMN sha256 text GENERATED ALWAYS AS"
        " (panestria.event_digest(id,goal_id,task_id,attempt_id,seq,kind,actor,trace_id,payload,"
        " schema_version,privacy_label)) STORED"
    )
    op.execute(
        "CREATE TRIGGER immutable_event BEFORE UPDATE OR DELETE ON panestria.task_event"
        " FOR EACH ROW EXECUTE FUNCTION panestria.immutable_memory_record()"
    )
    op.execute("""CREATE TABLE panestria.event_retention (
        goal_id uuid PRIMARY KEY REFERENCES panestria.goal(id), floor_seq bigint NOT NULL DEFAULT 0 CHECK(floor_seq>=0),
        row_version bigint NOT NULL DEFAULT 0 CHECK(row_version>=0))""")


def downgrade() -> None:
    op.execute("DROP TABLE panestria.event_retention")
    op.execute("DROP TRIGGER immutable_event ON panestria.task_event")
    op.execute(
        "ALTER TABLE panestria.task_event DROP COLUMN sha256, DROP COLUMN privacy_label, DROP COLUMN schema_version"
    )
    op.execute("DROP FUNCTION panestria.event_digest(uuid,uuid,uuid,uuid,bigint,text,text,text,jsonb,integer,text)")
