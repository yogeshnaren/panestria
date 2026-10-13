"""Normalized consented memory with immutable source/revision and scoped FTS."""

from alembic import op

revision = "0010_memory"
down_revision = "0009_browser_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE panestria.memory_source (
        id uuid PRIMARY KEY, owner_id uuid NOT NULL, project_id uuid NOT NULL,
        source_uri text NOT NULL, body text NOT NULL,
        sha256 char(64) NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'),
        privacy_label text NOT NULL CHECK(privacy_label IN ('PUBLIC','PRIVATE','RESTRICTED')),
        consented_by uuid NOT NULL REFERENCES panestria.principal(id),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        UNIQUE(id,owner_id,project_id),
        FOREIGN KEY(project_id,owner_id) REFERENCES panestria.project(id,owner_id))""")
    op.execute("""CREATE TABLE panestria.memory_item (
        id uuid PRIMARY KEY, owner_id uuid NOT NULL, project_id uuid NOT NULL,
        kind text NOT NULL CHECK(kind IN ('fact','preference','procedure')),
        current_revision integer NOT NULL DEFAULT 1 CHECK(current_revision>0),
        row_version bigint NOT NULL DEFAULT 0 CHECK(row_version>=0),
        status text NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','SUPPRESSED')),
        pinned boolean NOT NULL DEFAULT false, conflict_key text,
        valid_from timestamptz NOT NULL DEFAULT clock_timestamp(), valid_until timestamptz, retain_until timestamptz,
        UNIQUE(id,owner_id,project_id),
        CHECK(valid_until IS NULL OR valid_until>valid_from),
        FOREIGN KEY(project_id,owner_id) REFERENCES panestria.project(id,owner_id))""")
    op.execute("""CREATE TABLE panestria.memory_revision (
        id uuid PRIMARY KEY, item_id uuid NOT NULL, owner_id uuid NOT NULL, project_id uuid NOT NULL,
        version integer NOT NULL CHECK(version>0), source_id uuid NOT NULL,
        body text NOT NULL, sha256 char(64) NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'),
        search_document tsvector GENERATED ALWAYS AS (to_tsvector('english',body)) STORED,
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        UNIQUE(item_id,version), UNIQUE(id,item_id,owner_id,project_id),
        FOREIGN KEY(item_id,owner_id,project_id) REFERENCES panestria.memory_item(id,owner_id,project_id),
        FOREIGN KEY(source_id,owner_id,project_id) REFERENCES panestria.memory_source(id,owner_id,project_id))""")
    op.execute(
        "ALTER TABLE panestria.memory_item ADD CONSTRAINT current_memory_revision"
        " FOREIGN KEY(id,current_revision) REFERENCES panestria.memory_revision(item_id,version)"
        " DEFERRABLE INITIALLY DEFERRED"
    )
    op.execute("""CREATE TABLE panestria.context_pack (
        id uuid PRIMARY KEY, owner_id uuid NOT NULL, project_id uuid NOT NULL,
        request_id uuid NOT NULL, sha256 char(64) NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'),
        privacy_label text NOT NULL CHECK(privacy_label IN ('PUBLIC','PRIVATE','RESTRICTED')),
        metadata jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        UNIQUE(id,owner_id,project_id),
        FOREIGN KEY(project_id,owner_id) REFERENCES panestria.project(id,owner_id))""")
    op.execute("""CREATE TABLE panestria.memory_use_event (
        id uuid PRIMARY KEY, owner_id uuid NOT NULL, project_id uuid NOT NULL, item_id uuid NOT NULL,
        revision_id uuid NOT NULL, context_pack_id uuid,
        stage text NOT NULL CHECK(stage IN (
            'retrieved','included','used_by_worker','judged_unused','candidate_helped')),
        observer_kind text NOT NULL CHECK(observer_kind IN ('application','worker_report','human','verifier')),
        observer_id text NOT NULL, confidence double precision CHECK(confidence BETWEEN 0 AND 1),
        evidence_ref text, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        FOREIGN KEY(revision_id,item_id,owner_id,project_id)
            REFERENCES panestria.memory_revision(id,item_id,owner_id,project_id),
        FOREIGN KEY(context_pack_id,owner_id,project_id) REFERENCES panestria.context_pack(id,owner_id,project_id),
        CHECK(stage<>'candidate_helped' OR (observer_kind IN ('human','verifier') AND evidence_ref IS NOT NULL)),
        CHECK(observer_kind<>'worker_report' OR confidence IS NULL OR confidence<=0.5))""")
    op.execute("CREATE INDEX ix_memory_fts ON panestria.memory_revision USING gin(search_document)")
    op.execute("CREATE INDEX ix_memory_scope ON panestria.memory_item(owner_id,project_id,status)")
    op.execute("""CREATE FUNCTION panestria.immutable_memory_record() RETURNS trigger LANGUAGE plpgsql AS $fn$
        BEGIN RAISE EXCEPTION 'memory history is immutable'; END; $fn$""")
    for table in ("memory_source", "memory_revision", "context_pack", "memory_use_event"):
        op.execute(
            f"CREATE TRIGGER immutable_memory BEFORE UPDATE OR DELETE ON panestria.{table}"
            " FOR EACH ROW EXECUTE FUNCTION panestria.immutable_memory_record()"
        )


def downgrade() -> None:
    op.execute("ALTER TABLE panestria.memory_item DROP CONSTRAINT current_memory_revision")
    op.execute(
        "DROP TABLE panestria.memory_use_event,panestria.context_pack,panestria.memory_revision,"
        " panestria.memory_item,panestria.memory_source"
    )
    op.execute("DROP FUNCTION panestria.immutable_memory_record()")
