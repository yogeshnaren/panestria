"""Conservative task-wide source/body reservations and per-hop disclosure before DNS."""

from alembic import op

revision = "0031_fetch_admission"
down_revision = "0030_search_admission"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE panestria.fetch_plan (
        task_id uuid PRIMARY KEY,request_id uuid NOT NULL,
        request_sha256 char(64) NOT NULL CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
        contract_sha256 char(64) NOT NULL CHECK(contract_sha256 ~ '^[0-9a-f]{64}$'),
        policy_sha256 char(64) NOT NULL CHECK(policy_sha256 ~ '^[0-9a-f]{64}$'),
        configuration_sha256 char(64) NOT NULL CHECK(configuration_sha256 ~ '^[0-9a-f]{64}$'),
        plan_sha256 char(64) NOT NULL CHECK(plan_sha256 ~ '^[0-9a-f]{64}$'),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        UNIQUE(task_id,request_id),
        FOREIGN KEY(request_id,task_id) REFERENCES panestria.research_request(id,task_id))""")
    op.execute("""CREATE TABLE panestria.fetch_dispatch (
        id uuid PRIMARY KEY,task_id uuid NOT NULL,request_id uuid NOT NULL,
        attempt_id uuid NOT NULL,lease_epoch bigint NOT NULL CHECK(lease_epoch>0),
        ordinal integer NOT NULL CHECK(ordinal BETWEEN 1 AND 16),
        url_sha256 char(64) NOT NULL CHECK(url_sha256 ~ '^[0-9a-f]{64}$'),
        reserved_body_bytes integer NOT NULL CHECK(reserved_body_bytes BETWEEN 2 AND 2097153),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        UNIQUE(task_id,ordinal),UNIQUE(task_id,url_sha256),UNIQUE(id,task_id,request_id),
        FOREIGN KEY(task_id,request_id) REFERENCES panestria.fetch_plan(task_id,request_id),
        FOREIGN KEY(attempt_id,task_id) REFERENCES panestria.task_attempt(id,task_id))""")
    op.execute("""CREATE TABLE panestria.fetch_hop (
        dispatch_id uuid NOT NULL REFERENCES panestria.fetch_dispatch(id),
        ordinal integer NOT NULL CHECK(ordinal BETWEEN 0 AND 5),
        url_sha256 char(64) NOT NULL CHECK(url_sha256 ~ '^[0-9a-f]{64}$'),
        host_sha256 char(64) NOT NULL CHECK(host_sha256 ~ '^[0-9a-f]{64}$'),
        url_bytes integer NOT NULL CHECK(url_bytes BETWEEN 1 AND 2048),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        PRIMARY KEY(dispatch_id,ordinal),UNIQUE(dispatch_id,url_sha256))""")
    op.execute("""CREATE TABLE panestria.fetch_outcome (
        dispatch_id uuid PRIMARY KEY,task_id uuid NOT NULL,request_id uuid NOT NULL,
        status text NOT NULL CHECK(status IN('RETAINED','FETCH_ERROR','READER_ERROR','UNKNOWN')),
        diagnostic text NOT NULL CHECK(diagnostic IN('retained','fetch_size_limit','fetch_timeout','fetch_http_error',
            'fetch_denied_or_unavailable','reader_truncated','reader_unsupported','reader_unavailable','unconfirmed')),
        snapshot_id uuid REFERENCES panestria.research_source_capture(snapshot_id),
        source_metadata_sha256 char(64),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        CHECK((status='RETAINED' AND diagnostic='retained') OR
            (status='FETCH_ERROR' AND diagnostic IN('fetch_size_limit','fetch_timeout',
                'fetch_http_error','fetch_denied_or_unavailable')) OR
            (status='READER_ERROR' AND diagnostic IN('reader_truncated','reader_unsupported','reader_unavailable')) OR
            (status='UNKNOWN' AND diagnostic='unconfirmed')),
        CHECK((status='RETAINED' AND snapshot_id IS NOT NULL AND source_metadata_sha256 IS NOT NULL)
            OR (status<>'RETAINED' AND snapshot_id IS NULL AND source_metadata_sha256 IS NULL)),
        FOREIGN KEY(dispatch_id,task_id,request_id) REFERENCES panestria.fetch_dispatch(id,task_id,request_id),
        FOREIGN KEY(snapshot_id,request_id,task_id,source_metadata_sha256)
            REFERENCES panestria.research_source_snapshot(id,request_id,task_id,body_sha256))""")
    for table in ("fetch_plan", "fetch_dispatch", "fetch_hop", "fetch_outcome"):
        op.execute(
            f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON panestria.{table} "
            "FOR EACH ROW EXECUTE FUNCTION panestria.immutable_memory_record()"
        )


def downgrade() -> None:
    op.execute(
        "LOCK TABLE panestria.fetch_plan,panestria.fetch_dispatch,panestria.fetch_hop,"
        "panestria.fetch_outcome IN ACCESS EXCLUSIVE MODE"
    )
    if op.get_bind().exec_driver_sql("SELECT EXISTS(SELECT 1 FROM panestria.fetch_plan)").scalar():
        raise RuntimeError("fetch admission audit exists; use forward repair or a reviewed backup")
    for table in ("fetch_outcome", "fetch_hop", "fetch_dispatch", "fetch_plan"):
        op.execute(f"DROP TABLE panestria.{table}")
