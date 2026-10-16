"""Immutable connection declarations and exact owner decisions, not effect permits."""

from alembic import op

revision = "0027_connection_reviews"
down_revision = "0026_claim_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE panestria.connection_grant (
        id uuid PRIMARY KEY, owner_id uuid NOT NULL, project_id uuid NOT NULL,
        current_version integer NOT NULL DEFAULT 0 CHECK(current_version BETWEEN 0 AND 1000001),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        UNIQUE(id,owner_id,project_id),
        FOREIGN KEY(project_id,owner_id) REFERENCES panestria.project(id,owner_id))""")
    op.execute("""CREATE TABLE panestria.connection_grant_review (
        id uuid PRIMARY KEY, grant_id uuid NOT NULL, owner_id uuid NOT NULL, project_id uuid NOT NULL,
        goal_id uuid NOT NULL, task_id uuid NOT NULL,
        expected_version integer NOT NULL CHECK(expected_version BETWEEN 0 AND 1000000),
        operation text NOT NULL CHECK(operation IN ('REPLACE','REVOKE')),
        request_sha256 char(64) NOT NULL CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
        manifest_sha256 char(64) NOT NULL CHECK(manifest_sha256 ~ '^[0-9a-f]{64}$'),
        manifest_body jsonb NOT NULL CHECK(jsonb_typeof(manifest_body)='object'
            AND octet_length(manifest_body::text) BETWEEN 1 AND 32768),
        policy_ref text NOT NULL CHECK(policy_ref ~ '^project-policy:[1-9][0-9]{0,18}:[0-9a-f]{64}$'),
        effect_digest char(64) NOT NULL CHECK(effect_digest ~ '^[0-9a-f]{64}$'),
        expires_at timestamptz NOT NULL,
        seq bigint NOT NULL UNIQUE DEFAULT nextval(pg_get_serial_sequence('panestria.task_event','seq')::regclass),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        CHECK(expires_at>created_at AND expires_at<=created_at+interval '15 minutes'),
        CHECK(operation<>'REVOKE' OR expected_version>0),
        UNIQUE(id,grant_id,owner_id,project_id,manifest_sha256,operation,policy_ref),
        UNIQUE(id,grant_id,owner_id,project_id,expected_version,effect_digest),
        FOREIGN KEY(grant_id,owner_id,project_id) REFERENCES panestria.connection_grant(id,owner_id,project_id),
        FOREIGN KEY(goal_id,project_id,owner_id) REFERENCES panestria.goal(id,project_id,owner_id),
        FOREIGN KEY(task_id,goal_id) REFERENCES panestria.task(id,goal_id))""")
    op.execute("""CREATE TABLE panestria.connection_grant_decision (
        review_id uuid PRIMARY KEY, grant_id uuid NOT NULL, owner_id uuid NOT NULL, project_id uuid NOT NULL,
        expected_version integer NOT NULL CHECK(expected_version BETWEEN 0 AND 1000000),
        effect_digest char(64) NOT NULL CHECK(effect_digest ~ '^[0-9a-f]{64}$'),
        decision text NOT NULL CHECK(decision IN ('APPROVED','DENIED')),
        granted_version integer CHECK(granted_version BETWEEN 1 AND 1000001),
        decided_by uuid NOT NULL REFERENCES panestria.principal(id),
        decided_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        seq bigint NOT NULL UNIQUE DEFAULT nextval(pg_get_serial_sequence('panestria.task_event','seq')::regclass),
        CHECK(decided_by=owner_id),
        CHECK((decision='APPROVED' AND granted_version IS NOT NULL AND granted_version=expected_version+1)
            OR (decision='DENIED' AND granted_version IS NULL)),
        UNIQUE(review_id,grant_id,granted_version,decision),
        FOREIGN KEY(review_id,grant_id,owner_id,project_id,expected_version,effect_digest)
            REFERENCES panestria.connection_grant_review
                (id,grant_id,owner_id,project_id,expected_version,effect_digest))""")
    op.execute("""CREATE TABLE panestria.connection_grant_revision (
        grant_id uuid NOT NULL, version integer NOT NULL CHECK(version BETWEEN 1 AND 1000001),
        owner_id uuid NOT NULL, project_id uuid NOT NULL, review_id uuid NOT NULL UNIQUE,
        manifest_sha256 char(64) NOT NULL CHECK(manifest_sha256 ~ '^[0-9a-f]{64}$'),
        operation text NOT NULL CHECK(operation IN ('REPLACE','REVOKE')),
        policy_ref text NOT NULL,
        decision text NOT NULL DEFAULT 'APPROVED' CHECK(decision='APPROVED'),
        seq bigint NOT NULL UNIQUE DEFAULT nextval(pg_get_serial_sequence('panestria.task_event','seq')::regclass),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        PRIMARY KEY(grant_id,version),
        UNIQUE(grant_id,version,review_id),
        FOREIGN KEY(grant_id,owner_id,project_id) REFERENCES panestria.connection_grant(id,owner_id,project_id),
        FOREIGN KEY(review_id,grant_id,owner_id,project_id,manifest_sha256,operation,policy_ref)
            REFERENCES panestria.connection_grant_review
                (id,grant_id,owner_id,project_id,manifest_sha256,operation,policy_ref),
        FOREIGN KEY(review_id,grant_id,version,decision)
            REFERENCES panestria.connection_grant_decision(review_id,grant_id,granted_version,decision)
            DEFERRABLE INITIALLY DEFERRED)""")
    op.execute(
        "ALTER TABLE panestria.connection_grant_decision ADD CONSTRAINT grant_decision_revision "
        "FOREIGN KEY(grant_id,granted_version,review_id) "
        "REFERENCES panestria.connection_grant_revision(grant_id,version,review_id) "
        "DEFERRABLE INITIALLY DEFERRED"
    )
    for table in ("connection_grant_review", "connection_grant_decision", "connection_grant_revision"):
        op.execute(
            f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON panestria.{table} "
            "FOR EACH ROW EXECUTE FUNCTION panestria.immutable_memory_record()"
        )
    op.execute("""CREATE FUNCTION panestria.guard_connection_grant() RETURNS trigger LANGUAGE plpgsql AS $fn$
        BEGIN
          IF TG_OP='DELETE' THEN RAISE EXCEPTION 'connection grant audit is immutable'; END IF;
          IF (NEW.id,NEW.owner_id,NEW.project_id,NEW.created_at) IS DISTINCT FROM
             (OLD.id,OLD.owner_id,OLD.project_id,OLD.created_at)
             OR NEW.current_version<>OLD.current_version+1 THEN
            RAISE EXCEPTION 'invalid connection grant pointer transition';
          END IF;
          RETURN NEW;
        END; $fn$""")
    op.execute(
        "CREATE TRIGGER guard_connection_grant BEFORE UPDATE OR DELETE ON panestria.connection_grant "
        "FOR EACH ROW EXECUTE FUNCTION panestria.guard_connection_grant()"
    )
    op.execute("""CREATE FUNCTION panestria.check_connection_grant_pointer() RETURNS trigger LANGUAGE plpgsql AS $fn$
        DECLARE identifier uuid; pointer integer; latest integer; amount bigint;
        BEGIN
          IF TG_TABLE_NAME='connection_grant' THEN identifier:=NEW.id; ELSE identifier:=NEW.grant_id; END IF;
          SELECT current_version INTO pointer FROM panestria.connection_grant WHERE id=identifier;
          SELECT COALESCE(max(version),0),count(*) INTO latest,amount
            FROM panestria.connection_grant_revision WHERE grant_id=identifier;
          IF pointer IS NULL OR pointer<>latest OR latest<>amount THEN
            RAISE EXCEPTION 'connection grant pointer/revision mismatch';
          END IF;
          RETURN NULL;
        END; $fn$""")
    for table in ("connection_grant", "connection_grant_revision"):
        op.execute(
            f"CREATE CONSTRAINT TRIGGER complete_{table} AFTER INSERT OR UPDATE ON panestria.{table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION panestria.check_connection_grant_pointer()"
        )


def downgrade() -> None:
    op.execute("LOCK TABLE panestria.connection_grant IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().exec_driver_sql("SELECT EXISTS(SELECT 1 FROM panestria.connection_grant)").scalar():
        raise RuntimeError("connection grant audit exists; use forward repair or a reviewed backup")
    op.execute("ALTER TABLE panestria.connection_grant_decision DROP CONSTRAINT grant_decision_revision")
    op.execute(
        "DROP TABLE panestria.connection_grant_revision,panestria.connection_grant_decision,"
        "panestria.connection_grant_review,panestria.connection_grant"
    )
    op.execute("DROP FUNCTION panestria.check_connection_grant_pointer(),panestria.guard_connection_grant()")
