"""A task-wide immutable query budget and append-only dispatch/outcome audit."""

from alembic import op

revision = "0030_search_admission"
down_revision = "0029_quota_observations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE panestria.search_plan (
        task_id uuid PRIMARY KEY, request_id uuid NOT NULL,
        request_sha256 char(64) NOT NULL CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
        contract_sha256 char(64) NOT NULL CHECK(contract_sha256 ~ '^[0-9a-f]{64}$'),
        policy_sha256 char(64) NOT NULL CHECK(policy_sha256 ~ '^[0-9a-f]{64}$'),
        configuration_sha256 char(64) NOT NULL CHECK(configuration_sha256 ~ '^[0-9a-f]{64}$'),
        max_queries integer NOT NULL CHECK(max_queries BETWEEN 1 AND 16),
        plan_sha256 char(64) NOT NULL CHECK(plan_sha256 ~ '^[0-9a-f]{64}$'),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        UNIQUE(task_id,request_id,configuration_sha256),
        FOREIGN KEY(request_id,task_id) REFERENCES panestria.research_request(id,task_id))""")
    op.execute("""CREATE TABLE panestria.search_dispatch (
        id uuid PRIMARY KEY, task_id uuid NOT NULL REFERENCES panestria.search_plan(task_id),
        request_id uuid NOT NULL, configuration_sha256 char(64) NOT NULL,
        attempt_id uuid NOT NULL, lease_epoch bigint NOT NULL CHECK(lease_epoch>0),
        ordinal integer NOT NULL CHECK(ordinal BETWEEN 1 AND 16),
        query_sha256 char(64) NOT NULL CHECK(query_sha256 ~ '^[0-9a-f]{64}$'),
        disclosure_sha256 char(64) NOT NULL CHECK(disclosure_sha256 ~ '^[0-9a-f]{64}$'),
        disclosure jsonb NOT NULL CHECK(jsonb_typeof(disclosure)='object' AND octet_length(disclosure::text)<=4096),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        UNIQUE(task_id,ordinal), UNIQUE(task_id,query_sha256),
        FOREIGN KEY(attempt_id,task_id) REFERENCES panestria.task_attempt(id,task_id),
        FOREIGN KEY(task_id,request_id,configuration_sha256)
            REFERENCES panestria.search_plan(task_id,request_id,configuration_sha256),
        CHECK(disclosure ?& ARRAY['schema_version','request_id','scope','provider','configuration_sha256',
            'request_sha256','query_sha256','query_bytes','privacy_class','upstream_disclosure']),
        CHECK(disclosure - ARRAY['schema_version','request_id','scope','provider','configuration_sha256',
            'request_sha256','query_sha256','query_bytes','privacy_class','upstream_disclosure']='{}'::jsonb),
        CHECK(disclosure->'schema_version'='1'::jsonb),
        CHECK((disclosure->>'request_id'=request_id::text) IS TRUE),
        CHECK((disclosure->'scope'->>'task_id'=task_id::text) IS TRUE),
        CHECK((disclosure->>'provider'='searxng-local') IS TRUE),
        CHECK((disclosure->>'configuration_sha256'=configuration_sha256) IS TRUE),
        CHECK((disclosure->>'query_sha256'=query_sha256) IS TRUE),
        CHECK((disclosure->>'request_sha256' ~ '^[0-9a-f]{64}$') IS TRUE),
        CHECK((disclosure->>'privacy_class'='PUBLIC') IS TRUE),
        CHECK((disclosure->>'upstream_disclosure'='POSSIBLE_NOT_OBSERVED') IS TRUE),
        CHECK(CASE WHEN jsonb_typeof(disclosure->'query_bytes')='number'
            AND disclosure->>'query_bytes' ~ '^[0-9]{1,3}$'
            THEN (disclosure->>'query_bytes')::integer BETWEEN 1 AND 512 ELSE false END))""")
    op.execute("""CREATE TABLE panestria.search_outcome (
        dispatch_id uuid PRIMARY KEY REFERENCES panestria.search_dispatch(id),
        status text NOT NULL CHECK(status IN ('RETURNED','UNAVAILABLE','UNKNOWN')),
        response_sha256 char(64) CHECK(response_sha256 ~ '^[0-9a-f]{64}$'),
        candidate_count integer CHECK(candidate_count BETWEEN 0 AND 16),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        CHECK((status='RETURNED' AND response_sha256 IS NOT NULL AND candidate_count IS NOT NULL)
            OR (status<>'RETURNED' AND response_sha256 IS NULL AND candidate_count IS NULL)))""")
    for table in ("search_plan", "search_dispatch", "search_outcome"):
        op.execute(
            f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON panestria.{table} "
            "FOR EACH ROW EXECUTE FUNCTION panestria.immutable_memory_record()"
        )


def downgrade() -> None:
    op.execute(
        "LOCK TABLE panestria.search_plan,panestria.search_dispatch,panestria.search_outcome IN ACCESS EXCLUSIVE MODE"
    )
    if op.get_bind().exec_driver_sql("SELECT EXISTS(SELECT 1 FROM panestria.search_plan)").scalar():
        raise RuntimeError("search admission audit exists; use forward repair or a reviewed backup")
    for table in ("search_outcome", "search_dispatch", "search_plan"):
        op.execute(f"DROP TABLE panestria.{table}")
