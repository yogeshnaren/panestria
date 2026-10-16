"""Immutable scoped quota metadata, distinct from cash or runtime authorization."""

from alembic import op

revision = "0029_quota_observations"
down_revision = "0028_sandbox_launch_intent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE panestria.quota_observation (
        id uuid PRIMARY KEY, owner_id uuid NOT NULL, project_id uuid NOT NULL,
        goal_id uuid NOT NULL, task_id uuid NOT NULL,
        scope_sha256 char(64) NOT NULL CHECK(scope_sha256 ~ '^[0-9a-f]{64}$'),
        source text NOT NULL CHECK(source IN ('PROVIDER_REPORTED','OWNER_REPORTED','ESTIMATED','UNKNOWN')),
        observed_at timestamptz NOT NULL, resets_at timestamptz,
        fresh_for_seconds integer NOT NULL CHECK(fresh_for_seconds BETWEEN 1 AND 86400),
        body jsonb NOT NULL, body_sha256 char(64) NOT NULL CHECK(body_sha256 ~ '^[0-9a-f]{64}$'),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        FOREIGN KEY(goal_id,project_id,owner_id) REFERENCES panestria.goal(id,project_id,owner_id),
        FOREIGN KEY(task_id,goal_id) REFERENCES panestria.task(id,goal_id),
        CHECK(observed_at<=created_at), CHECK(resets_at IS NULL OR resets_at>observed_at),
        CHECK(jsonb_typeof(body)='object' AND octet_length(body::text) BETWEEN 1 AND 4096),
        CHECK(body ?& ARRAY['schema_version','observation_id','scope','source','remaining','unit',
            'observed_at','resets_at','fresh_for_seconds','source_sha256']),
        CHECK(body - ARRAY['schema_version','observation_id','scope','source','remaining','unit',
            'observed_at','resets_at','fresh_for_seconds','source_sha256']='{}'::jsonb),
        CHECK(body->>'schema_version'='1' AND jsonb_typeof(body->'schema_version')='number'),
        CHECK(body->>'observation_id'=id::text AND jsonb_typeof(body->'observation_id')='string'),
        CHECK(body->>'source'=source AND jsonb_typeof(body->'source')='string'),
        CHECK(jsonb_typeof(body->'scope')='object'),
        CHECK(body->'remaining'='null'::jsonb OR
            (jsonb_typeof(body->'remaining')='string' AND body->>'remaining' ~ '^(0|[1-9][0-9]{0,11})([.][0-9]{1,3})?$'
             AND (body->>'unit' IN ('percent','tokens','requests')) IS TRUE)),
        CHECK(source<>'UNKNOWN' OR body->'remaining'='null'::jsonb),
        CHECK(CASE WHEN jsonb_typeof(body->'remaining')='string'
            AND body->>'remaining' ~ '^(0|[1-9][0-9]{0,11})([.][0-9]{1,3})?$'
            THEN CASE WHEN body->>'unit'='percent' THEN (body->>'remaining')::numeric<=100
                WHEN body->>'unit' IN ('tokens','requests') THEN mod((body->>'remaining')::numeric,1)=0
                ELSE false END ELSE body->'remaining'='null'::jsonb END),
        CHECK(body->'unit'='null'::jsonb OR (jsonb_typeof(body->'unit')='string'
            AND (body->>'unit' IN ('percent','tokens','requests')) IS TRUE)),
        CHECK((source IN ('PROVIDER_REPORTED','ESTIMATED') AND jsonb_typeof(body->'source_sha256')='string'
                AND body->>'source_sha256' ~ '^[0-9a-f]{64}$')
            OR (source IN ('OWNER_REPORTED','UNKNOWN') AND body->'source_sha256'='null'::jsonb)),
        CHECK(body->>'fresh_for_seconds'=fresh_for_seconds::text
            AND jsonb_typeof(body->'fresh_for_seconds')='number'),
        CHECK(jsonb_typeof(body->'observed_at')='string' AND (body->>'observed_at')::timestamptz=observed_at),
        CHECK((body->'resets_at'='null'::jsonb AND resets_at IS NULL)
            OR (jsonb_typeof(body->'resets_at')='string'
                AND (body->>'resets_at')::timestamptz=resets_at AND resets_at IS NOT NULL)))""")
    op.execute("""CREATE INDEX quota_scope_latest ON panestria.quota_observation
        (owner_id,project_id,scope_sha256,source,observed_at DESC,created_at DESC,id DESC)""")
    op.execute("""CREATE TRIGGER immutable_quota_observation BEFORE UPDATE OR DELETE ON panestria.quota_observation
        FOR EACH ROW EXECUTE FUNCTION panestria.immutable_memory_record()""")


def downgrade() -> None:
    op.execute("LOCK TABLE panestria.quota_observation IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().exec_driver_sql("SELECT EXISTS(SELECT 1 FROM panestria.quota_observation)").scalar():
        raise RuntimeError("quota observation audit exists; use forward repair or a reviewed backup")
    op.execute("DROP TABLE panestria.quota_observation")
