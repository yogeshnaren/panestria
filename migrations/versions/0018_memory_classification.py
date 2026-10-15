"""Preserve source labels with an atomic, immutable canonical interpretation."""

from alembic import op

revision = "0018_memory_classification"
down_revision = "0017_worker_invocation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Serialize the backfill/trigger boundary with old and new application writes.
    op.execute("LOCK TABLE panestria.memory_source IN SHARE ROW EXCLUSIVE MODE")
    op.execute(
        "ALTER TABLE panestria.memory_source ADD CONSTRAINT memory_source_classification_identity"
        " UNIQUE(id,owner_id,project_id,sha256,privacy_label,consented_by)"
    )
    op.execute("""CREATE TABLE panestria.memory_classification (
        source_id uuid PRIMARY KEY, owner_id uuid NOT NULL, project_id uuid NOT NULL,
        source_sha256 char(64) NOT NULL,
        original_label text NOT NULL, effective_label text NOT NULL,
        interpretation text NOT NULL, resolver_version integer NOT NULL CHECK(resolver_version=1),
        origin text NOT NULL CHECK(origin IN ('MIGRATION','SOURCE_WRITE')),
        consented_by uuid NOT NULL, policy_ref text,
        review_id uuid, review_effect_digest char(64), review_decided_by uuid,
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        FOREIGN KEY(source_id,owner_id,project_id,source_sha256,original_label,consented_by)
            REFERENCES panestria.memory_source(id,owner_id,project_id,sha256,privacy_label,consented_by),
        FOREIGN KEY(review_id,owner_id,project_id) REFERENCES panestria.memory_review(id,owner_id,project_id),
        CHECK(effective_label IN ('PUBLIC','INTERNAL','CONFIDENTIAL','RESTRICTED')),
        CHECK((original_label='PRIVATE' AND effective_label='RESTRICTED' AND interpretation='LEGACY_RESTRICTED')
            OR (original_label IN ('PUBLIC','INTERNAL','CONFIDENTIAL','RESTRICTED')
                AND original_label=effective_label AND interpretation='CANONICAL')),
        CHECK((review_id IS NULL AND review_effect_digest IS NULL AND review_decided_by IS NULL)
            OR (review_id IS NOT NULL AND review_effect_digest IS NOT NULL AND review_effect_digest ~ '^[0-9a-f]{64}$'
                AND review_decided_by IS NOT NULL AND review_decided_by=owner_id AND policy_ref IS NOT NULL)))""")
    op.execute("CREATE UNIQUE INDEX ix_classification_review_once ON panestria.memory_classification(review_id)")
    op.execute("""INSERT INTO panestria.memory_classification
        (source_id,owner_id,project_id,source_sha256,original_label,effective_label,interpretation,
         resolver_version,origin,consented_by,policy_ref,review_id,review_effect_digest,review_decided_by)
        SELECT s.id,s.owner_id,s.project_id,s.sha256,s.privacy_label,
            CASE WHEN s.privacy_label='PRIVATE' THEN 'RESTRICTED' ELSE s.privacy_label END,
            CASE WHEN s.privacy_label='PRIVATE' THEN 'LEGACY_RESTRICTED' ELSE 'CANONICAL' END,
            1,'MIGRATION',s.consented_by,
            CASE WHEN s.review_id IS NOT NULL THEN r.policy_ref ELSE NULL END,
            s.review_id,r.effect_digest,r.decided_by
        FROM panestria.memory_source s LEFT JOIN panestria.memory_review r ON r.id=s.review_id
        AND r.owner_id=s.owner_id AND r.project_id=s.project_id""")
    # Fail rather than bless a legacy dangling/unconsumed/inconsistent review.
    op.execute("""DO $fn$ BEGIN
        IF EXISTS (SELECT 1 FROM panestria.memory_source s JOIN panestria.memory_review r ON r.id=s.review_id
            WHERE r.state<>'CONSUMED' OR r.decided_at IS NULL OR r.decided_by IS DISTINCT FROM s.owner_id
            OR r.proposed->>'label' IS DISTINCT FROM s.privacy_label
            OR r.proposed->>'body' IS DISTINCT FROM s.body
            OR r.proposed->>'source_uri' IS DISTINCT FROM s.source_uri) THEN
            RAISE EXCEPTION 'classification_review_invalid';
        END IF;
        END; $fn$""")
    op.execute("""CREATE FUNCTION panestria.record_memory_classification() RETURNS trigger LANGUAGE plpgsql AS $fn$
        DECLARE policy_ref_value text; review_digest char(64); review_actor uuid;
        BEGIN
            IF NEW.review_id IS NOT NULL THEN
                SELECT r.policy_ref,r.effect_digest,r.decided_by INTO policy_ref_value,review_digest,review_actor
                FROM panestria.memory_review r WHERE r.id=NEW.review_id
                    AND r.owner_id=NEW.owner_id AND r.project_id=NEW.project_id AND r.state='CONSUMED'
                    AND r.decided_by=NEW.owner_id AND r.decided_at IS NOT NULL
                    AND r.proposed->>'label'=NEW.privacy_label AND r.proposed->>'body'=NEW.body
                    AND r.proposed->>'source_uri'=NEW.source_uri;
                IF NOT FOUND THEN RAISE EXCEPTION 'classification_review_invalid'; END IF;
            ELSE
                SELECT 'project-policy:'||p.policy_version||':'||r.sha256::text INTO policy_ref_value
                FROM panestria.project p JOIN panestria.project_policy_revision r
                    ON r.project_id=p.id AND r.owner_id=p.owner_id AND r.version=p.policy_version
                WHERE p.id=NEW.project_id AND p.owner_id=NEW.owner_id;
            END IF;
            INSERT INTO panestria.memory_classification
                (source_id,owner_id,project_id,source_sha256,original_label,effective_label,interpretation,
                 resolver_version,origin,consented_by,policy_ref,review_id,review_effect_digest,review_decided_by)
                VALUES (NEW.id,NEW.owner_id,NEW.project_id,NEW.sha256,NEW.privacy_label,
                    CASE WHEN NEW.privacy_label='PRIVATE' THEN 'RESTRICTED' ELSE NEW.privacy_label END,
                    CASE WHEN NEW.privacy_label='PRIVATE' THEN 'LEGACY_RESTRICTED' ELSE 'CANONICAL' END,
                    1,'SOURCE_WRITE',NEW.consented_by,policy_ref_value,NEW.review_id,review_digest,review_actor);
            RETURN NEW;
        END; $fn$""")
    op.execute("""CREATE TRIGGER source_classification AFTER INSERT ON panestria.memory_source
        FOR EACH ROW EXECUTE FUNCTION panestria.record_memory_classification()""")
    op.execute("""CREATE TRIGGER immutable_classification BEFORE UPDATE OR DELETE ON panestria.memory_classification
        FOR EACH ROW EXECUTE FUNCTION panestria.immutable_memory_record()""")


def downgrade() -> None:
    op.execute("LOCK TABLE panestria.memory_source IN SHARE ROW EXCLUSIVE MODE")
    if op.get_bind().exec_driver_sql("SELECT EXISTS(SELECT 1 FROM panestria.memory_classification)").scalar():
        raise RuntimeError("classification audit exists; use forward repair or a reviewed backup")
    op.execute("DROP TRIGGER source_classification ON panestria.memory_source")
    op.execute("DROP FUNCTION panestria.record_memory_classification()")
    op.execute("DROP TABLE panestria.memory_classification")
    op.execute("ALTER TABLE panestria.memory_source DROP CONSTRAINT memory_source_classification_identity")
