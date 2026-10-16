"""Immutable scoped source metadata and exact pinned artifact associations."""

from alembic import op

revision = "0024_source_snapshot"
down_revision = "0023_research_request"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE panestria.research_request ADD CONSTRAINT research_request_full_scope "
               "UNIQUE(id,owner_id,project_id,goal_id,task_id)")
    op.execute("""CREATE TABLE panestria.research_source_snapshot (
        id uuid PRIMARY KEY, request_id uuid NOT NULL,
        owner_id uuid NOT NULL, project_id uuid NOT NULL, goal_id uuid NOT NULL, task_id uuid NOT NULL,
        schema_version integer NOT NULL CHECK(schema_version=1),
        body jsonb NOT NULL CHECK(jsonb_typeof(body)='object' AND octet_length(body::text)<=32768),
        body_sha256 char(64) NOT NULL CHECK(body_sha256 ~ '^[0-9a-f]{64}$'),
        privacy_class text NOT NULL CHECK(privacy_class IN ('PUBLIC','INTERNAL','CONFIDENTIAL','RESTRICTED')),
        completeness text NOT NULL CHECK(completeness IN ('COMPLETE','TRUNCATED','UNSUPPORTED','ERROR')),
        seq bigint NOT NULL UNIQUE DEFAULT nextval(pg_get_serial_sequence('panestria.task_event','seq')::regclass),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        UNIQUE(id,task_id),
        FOREIGN KEY(request_id,owner_id,project_id,goal_id,task_id)
            REFERENCES panestria.research_request(id,owner_id,project_id,goal_id,task_id),
        CHECK(((body->>'schema_version')::integer=1) IS TRUE),
        CHECK((body->'snapshot'->>'snapshot_id'=id::text AND body->'snapshot'->>'request_id'=request_id::text) IS TRUE),
        CHECK((body->'snapshot'->'scope'->>'owner_id'=owner_id::text
          AND body->'snapshot'->'scope'->>'project_id'=project_id::text
          AND body->'snapshot'->'scope'->>'goal_id'=goal_id::text
          AND body->'snapshot'->'scope'->>'task_id'=task_id::text) IS TRUE),
        CHECK((body->'snapshot'->>'completeness'=completeness) IS TRUE),
        CHECK((jsonb_typeof(body->'fetch_receipt')='object') IS TRUE),
        CHECK((completeness<>'COMPLETE' OR (
          jsonb_typeof(body->'snapshot'->'raw')='object' AND jsonb_typeof(body->'snapshot'->'text')='object'
          AND jsonb_typeof(body->'reader_receipt')='object'
          AND (body->'snapshot'->>'http_status')::integer BETWEEN 200 AND 299
          AND body->'snapshot'->>'terminal_url' IS NOT NULL
          AND body->'snapshot'->>'content_type' IN ('text/plain','text/html','application/pdf')
          AND (body->'snapshot'->'raw'->>'size_bytes')::bigint>0
          AND (body->'snapshot'->'text'->>'size_bytes')::bigint>0
          AND body->'snapshot'->'error_code'='null'::jsonb)) IS TRUE))""")
    op.execute("""CREATE TABLE panestria.research_source_artifact (
        snapshot_id uuid NOT NULL, role text NOT NULL CHECK(role IN ('raw','text','fetch','reader','redirect')),
        ordinal integer NOT NULL CHECK(ordinal BETWEEN 0 AND 4 AND (role='redirect' OR ordinal=0)),
        reference jsonb NOT NULL CHECK(jsonb_typeof(reference)='object'),
        artifact_id uuid GENERATED ALWAYS AS ((reference->>'artifact_id')::uuid) STORED NOT NULL,
        task_id uuid GENERATED ALWAYS AS ((reference->>'task_id')::uuid) STORED NOT NULL,
        sha256 char(64) GENERATED ALWAYS AS ((reference->>'sha256')::char(64)) STORED NOT NULL,
        size_bytes bigint GENERATED ALWAYS AS ((reference->>'size_bytes')::bigint) STORED NOT NULL,
        privacy_class text GENERATED ALWAYS AS (reference->>'privacy_label') STORED NOT NULL,
        CHECK((reference->'schema_version'='1'::jsonb) IS TRUE),
        CHECK(reference->>'sha256' ~ '^[0-9a-f]{64}$'),
        CHECK(size_bytes BETWEEN 0 AND 2097152),
        CHECK(privacy_class IN ('PUBLIC','INTERNAL','CONFIDENTIAL','RESTRICTED')),
        PRIMARY KEY(snapshot_id,role,ordinal),
        FOREIGN KEY(snapshot_id,task_id) REFERENCES panestria.research_source_snapshot(id,task_id),
        FOREIGN KEY(artifact_id,task_id,sha256,size_bytes,privacy_class)
            REFERENCES panestria.artifact(id,task_id,sha256,size_bytes,privacy_class))""")
    for table in ("research_source_snapshot", "research_source_artifact"):
        op.execute(f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON panestria.{table} "
                   "FOR EACH ROW EXECUTE FUNCTION panestria.immutable_memory_record()")
    op.execute("""CREATE FUNCTION panestria.check_source_artifact_set() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE source_id uuid; stored jsonb; actual jsonb; expected jsonb;
    BEGIN
      IF TG_TABLE_NAME='research_source_snapshot' THEN source_id:=NEW.id; ELSE source_id:=NEW.snapshot_id; END IF;
      SELECT body INTO stored FROM panestria.research_source_snapshot WHERE id=source_id;
      IF stored IS NULL THEN RETURN NEW; END IF;
      SELECT jsonb_agg(jsonb_build_object('role',role,'ordinal',ordinal,'reference',reference) ORDER BY role,ordinal)
        INTO actual FROM panestria.research_source_artifact WHERE snapshot_id=source_id;
      SELECT jsonb_agg(jsonb_build_object('role',role,'ordinal',ordinal,'reference',reference) ORDER BY role,ordinal)
        INTO expected FROM (
          SELECT * FROM (VALUES
            ('raw',0,stored->'snapshot'->'raw'),('text',0,stored->'snapshot'->'text'),
            ('fetch',0,stored->'fetch_receipt'),('reader',0,stored->'reader_receipt')
          ) refs(role,ordinal,reference) WHERE jsonb_typeof(reference)='object'
          UNION ALL SELECT 'redirect',(ordinality-1)::integer,value
            FROM jsonb_array_elements(stored->'snapshot'->'redirect_receipts') WITH ORDINALITY
        ) required;
      IF actual IS DISTINCT FROM expected THEN
        RAISE EXCEPTION 'source artifact set mismatch' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$""")
    for table in ("research_source_snapshot", "research_source_artifact"):
        op.execute(f"CREATE CONSTRAINT TRIGGER source_artifact_set_{table} AFTER INSERT ON panestria.{table} "
                   "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION panestria.check_source_artifact_set()")


def downgrade() -> None:
    op.execute("LOCK TABLE panestria.research_source_snapshot,panestria.research_source_artifact "
               "IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().exec_driver_sql("SELECT EXISTS(SELECT 1 FROM panestria.research_source_snapshot)").scalar():
        raise RuntimeError("source snapshot audit exists; use forward repair or a reviewed backup")
    op.execute("DROP TABLE panestria.research_source_artifact")
    op.execute("DROP TABLE panestria.research_source_snapshot")
    op.execute("DROP FUNCTION panestria.check_source_artifact_set()")
    op.execute("ALTER TABLE panestria.research_request DROP CONSTRAINT research_request_full_scope")
