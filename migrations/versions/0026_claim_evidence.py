"""Immutable deterministic claim reports and exact retained-source passage bindings."""

from alembic import op

revision = "0026_claim_evidence"
down_revision = "0025_source_capture"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE panestria.research_source_snapshot ADD CONSTRAINT source_snapshot_claim_scope "
        "UNIQUE(id,request_id,task_id,body_sha256)"
    )
    op.execute("""CREATE TABLE panestria.research_claim (
        id uuid PRIMARY KEY, request_id uuid NOT NULL, owner_id uuid NOT NULL, project_id uuid NOT NULL,
        goal_id uuid NOT NULL, task_id uuid NOT NULL,
        payload_artifact_id uuid NOT NULL, payload_sha256 char(64) NOT NULL,
        payload_size_bytes bigint NOT NULL CHECK(payload_size_bytes BETWEEN 1 AND 262144),
        report_artifact_id uuid NOT NULL, report_sha256 char(64) NOT NULL,
        report_size_bytes bigint NOT NULL CHECK(report_size_bytes BETWEEN 1 AND 32768),
        privacy_class text NOT NULL CHECK(privacy_class IN ('PUBLIC','INTERNAL','CONFIDENTIAL','RESTRICTED')),
        draft_kind text NOT NULL CHECK(draft_kind IN ('FACT','INTERPRETATION','OPINION','QUESTION')),
        verdict text NOT NULL CHECK(verdict IN ('NO_EVIDENCE','INVALID_EVIDENCE','EVIDENCE_PRESENT')),
        verified_passage_count integer NOT NULL CHECK(verified_passage_count BETWEEN 0 AND 16),
        CHECK(verdict<>'EVIDENCE_PRESENT' OR verified_passage_count>0),
        CHECK(verdict<>'NO_EVIDENCE' OR verified_passage_count=0),
        support_status text NOT NULL CHECK(support_status='NOT_ASSESSED'),
        verifier_version text NOT NULL CHECK(verifier_version='source-citation-v1'),
        seq bigint NOT NULL UNIQUE DEFAULT nextval(pg_get_serial_sequence('panestria.task_event','seq')::regclass),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(), UNIQUE(id,request_id,task_id),
        FOREIGN KEY(request_id,owner_id,project_id,goal_id,task_id)
            REFERENCES panestria.research_request(id,owner_id,project_id,goal_id,task_id),
        FOREIGN KEY(payload_artifact_id,task_id,payload_sha256,payload_size_bytes,privacy_class)
            REFERENCES panestria.artifact(id,task_id,sha256,size_bytes,privacy_class),
        FOREIGN KEY(report_artifact_id,task_id,report_sha256,report_size_bytes,privacy_class)
            REFERENCES panestria.artifact(id,task_id,sha256,size_bytes,privacy_class))""")
    op.execute("""CREATE TABLE panestria.research_claim_passage (
        claim_id uuid NOT NULL, request_id uuid NOT NULL, task_id uuid NOT NULL,
        ordinal integer NOT NULL CHECK(ordinal BETWEEN 0 AND 15), snapshot_id uuid NOT NULL,
        source_metadata_sha256 char(64) NOT NULL, text_sha256 char(64) NOT NULL CHECK(text_sha256 ~ '^[0-9a-f]{64}$'),
        start_bytes integer NOT NULL CHECK(start_bytes>=0),
        end_bytes integer NOT NULL CHECK(end_bytes>start_bytes AND end_bytes<=2097152),
        normalization_version text NOT NULL CHECK(normalization_version='nfc-utf8-v1'),
        quote_matched boolean NOT NULL, PRIMARY KEY(claim_id,ordinal),
        FOREIGN KEY(claim_id,request_id,task_id) REFERENCES panestria.research_claim(id,request_id,task_id),
        FOREIGN KEY(snapshot_id,request_id,task_id,source_metadata_sha256)
            REFERENCES panestria.research_source_snapshot(id,request_id,task_id,body_sha256),
        FOREIGN KEY(snapshot_id) REFERENCES panestria.research_source_capture(snapshot_id))""")
    for table in ("research_claim", "research_claim_passage"):
        op.execute(
            f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON panestria.{table} "
            "FOR EACH ROW EXECUTE FUNCTION panestria.immutable_memory_record()"
        )
    op.execute("""CREATE FUNCTION panestria.check_claim_passage_count() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE target uuid; expected integer; actual bigint;
    BEGIN
      IF TG_TABLE_NAME='research_claim' THEN target:=NEW.id; ELSE target:=NEW.claim_id; END IF;
      SELECT verified_passage_count INTO expected FROM panestria.research_claim WHERE id=target;
      SELECT count(*) INTO actual FROM panestria.research_claim_passage WHERE claim_id=target;
      IF expected IS DISTINCT FROM actual THEN
        RAISE EXCEPTION 'claim passage count mismatch' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$""")
    for table in ("research_claim", "research_claim_passage"):
        op.execute(
            f"CREATE CONSTRAINT TRIGGER claim_passage_count_{table} AFTER INSERT ON panestria.{table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION panestria.check_claim_passage_count()"
        )


def downgrade() -> None:
    op.execute("LOCK TABLE panestria.research_claim,panestria.research_claim_passage IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().exec_driver_sql("SELECT EXISTS(SELECT 1 FROM panestria.research_claim)").scalar():
        raise RuntimeError("claim evidence audit exists; use forward repair or a reviewed backup")
    op.execute("DROP TABLE panestria.research_claim_passage")
    op.execute("DROP TABLE panestria.research_claim")
    op.execute("DROP FUNCTION panestria.check_claim_passage_count()")
    op.execute("ALTER TABLE panestria.research_source_snapshot DROP CONSTRAINT source_snapshot_claim_scope")
