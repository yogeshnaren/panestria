"""Bind restricted Ask to immutable ciphertext and omit profile-output hashes."""

from alembic import op

revision = "0021_profile_ask"
down_revision = "0020_profile_vault"
branch_labels = None
depends_on = None


def _guard(*, modes: bool) -> None:
    new = ",NEW.response_digest_mode" if modes else ""
    old = ",OLD.response_digest_mode" if modes else ""
    op.execute(f"""CREATE OR REPLACE FUNCTION panestria.guard_ask_request() RETURNS trigger LANGUAGE plpgsql AS $fn$
        BEGIN
            IF (NEW.id,NEW.owner_id,NEW.project_id,NEW.request_sha256,NEW.context_pack_id,NEW.model_ref,
                NEW.policy_ref,NEW.trace_id,NEW.deadline_at,NEW.created_at{new}) IS DISTINCT FROM
                (OLD.id,OLD.owner_id,OLD.project_id,OLD.request_sha256,OLD.context_pack_id,OLD.model_ref,
                 OLD.policy_ref,OLD.trace_id,OLD.deadline_at,OLD.created_at{old}) THEN
                RAISE EXCEPTION 'ask request identity is immutable'; END IF;
            IF OLD.state IN ('COMPLETED','UNAVAILABLE','CANCELLED') AND NEW IS DISTINCT FROM OLD THEN
                RAISE EXCEPTION 'terminal ask receipt is immutable'; END IF;
            RETURN NEW;
        END; $fn$""")


def upgrade() -> None:
    op.execute("""ALTER TABLE panestria.profile_revision ADD CONSTRAINT profile_revision_context_identity
        UNIQUE(id,profile_id,owner_id,project_id,version,key_id,ciphertext_sha256)""")
    op.execute("""CREATE TABLE panestria.ask_profile_context (
        request_id uuid NOT NULL, owner_id uuid NOT NULL, project_id uuid NOT NULL,
        source_revision_id uuid NOT NULL, profile_id uuid NOT NULL, profile_version integer NOT NULL,
        row_version integer NOT NULL CHECK(row_version>=0), key_id uuid NOT NULL,
        ciphertext_sha256 char(64) NOT NULL, request_body jsonb NOT NULL CHECK(jsonb_typeof(request_body)='object'),
        selection_sha256 char(64) NOT NULL CHECK(selection_sha256 ~ '^[0-9a-f]{64}$'),
        manifest_sha256 char(64) NOT NULL CHECK(manifest_sha256 ~ '^[0-9a-f]{64}$'),
        policy_ref text NOT NULL, render_version integer NOT NULL CHECK(render_version=1),
        privacy_label text NOT NULL CHECK(privacy_label='RESTRICTED'),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        PRIMARY KEY(request_id,owner_id,project_id),
        FOREIGN KEY(request_id,owner_id,project_id) REFERENCES panestria.ask_request(id,owner_id,project_id),
        FOREIGN KEY(source_revision_id,profile_id,owner_id,project_id,profile_version,key_id,ciphertext_sha256)
            REFERENCES panestria.profile_revision
                (id,profile_id,owner_id,project_id,version,key_id,ciphertext_sha256))""")
    op.execute("""CREATE TRIGGER immutable_profile_context BEFORE UPDATE OR DELETE ON panestria.ask_profile_context
        FOR EACH ROW EXECUTE FUNCTION panestria.immutable_memory_record()""")
    op.execute("""ALTER TABLE panestria.ask_request ADD COLUMN response_digest_mode text NOT NULL DEFAULT 'SHA256'
        CHECK(response_digest_mode IN ('SHA256','OMITTED_RESTRICTED_PROFILE'))""")
    constraints = (
        op.get_bind()
        .exec_driver_sql("""SELECT conname FROM pg_constraint
        WHERE conrelid='panestria.ask_request'::regclass AND contype='c'
        AND strpos(pg_get_constraintdef(oid),'state = ''COMPLETED''')>0
        AND strpos(pg_get_constraintdef(oid),'response_sha256 IS NOT NULL')>0""")
        .fetchall()
    )
    if len(constraints) != 1:
        raise RuntimeError("legacy_ask_receipt_constraint_missing")
    op.drop_constraint(constraints[0][0], "ask_request", schema="panestria", type_="check")
    op.create_check_constraint(
        "ask_receipt_digest_mode",
        "ask_request",
        """
        (response_digest_mode='SHA256' AND (state='COMPLETED')=(response_sha256 IS NOT NULL))
        OR (response_digest_mode='OMITTED_RESTRICTED_PROFILE' AND response_sha256 IS NULL)""",
        schema="panestria",
    )
    _guard(modes=True)
    op.execute("""CREATE FUNCTION panestria.require_profile_ask_binding() RETURNS trigger LANGUAGE plpgsql AS $fn$
        DECLARE request_row panestria.ask_request%ROWTYPE;
        BEGIN
            IF TG_TABLE_NAME='ask_request' THEN request_row:=NEW;
            ELSE
                SELECT a.* INTO request_row FROM panestria.ask_request a
                    WHERE (a.id,a.owner_id,a.project_id)=(NEW.request_id,NEW.owner_id,NEW.project_id);
            END IF;
            IF request_row.response_digest_mode='OMITTED_RESTRICTED_PROFILE' THEN
                IF NOT EXISTS (SELECT 1 FROM panestria.ask_profile_context p
                    JOIN panestria.context_pack c ON c.id=request_row.context_pack_id
                    WHERE (p.request_id,p.owner_id,p.project_id,p.policy_ref)=
                        (request_row.id,request_row.owner_id,request_row.project_id,request_row.policy_ref)
                    AND c.owner_id=request_row.owner_id AND c.project_id=request_row.project_id
                    AND c.privacy_label='RESTRICTED')
                THEN RAISE EXCEPTION 'profile_ask_binding_required'; END IF;
            ELSIF EXISTS (SELECT 1 FROM panestria.ask_profile_context p
                WHERE (p.request_id,p.owner_id,p.project_id)=
                    (request_row.id,request_row.owner_id,request_row.project_id))
            THEN RAISE EXCEPTION 'profile_ask_digest_mode_invalid'; END IF;
            RETURN NEW;
        END; $fn$""")
    op.execute("""CREATE CONSTRAINT TRIGGER profile_ask_binding AFTER INSERT OR UPDATE ON panestria.ask_request
        DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION panestria.require_profile_ask_binding()""")
    op.execute("""CREATE CONSTRAINT TRIGGER profile_context_receipt AFTER INSERT ON panestria.ask_profile_context
        DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION panestria.require_profile_ask_binding()""")


def downgrade() -> None:
    op.execute("LOCK TABLE panestria.ask_request,panestria.ask_profile_context IN ACCESS EXCLUSIVE MODE")
    if (
        op.get_bind()
        .exec_driver_sql("""SELECT EXISTS(SELECT 1 FROM panestria.ask_profile_context)
        OR EXISTS(SELECT 1 FROM panestria.ask_request WHERE response_digest_mode<>'SHA256')""")
        .scalar()
    ):
        raise RuntimeError("profile Ask audit exists; use forward repair or a reviewed backup")
    op.execute("DROP TRIGGER profile_ask_binding ON panestria.ask_request")
    op.execute("DROP TRIGGER profile_context_receipt ON panestria.ask_profile_context")
    op.execute("DROP FUNCTION panestria.require_profile_ask_binding()")
    _guard(modes=False)
    op.drop_constraint("ask_receipt_digest_mode", "ask_request", schema="panestria", type_="check")
    op.execute("ALTER TABLE panestria.ask_request DROP COLUMN response_digest_mode")
    op.create_check_constraint(
        "ask_request_check", "ask_request", "(state='COMPLETED')=(response_sha256 IS NOT NULL)", schema="panestria"
    )
    op.execute("DROP TABLE panestria.ask_profile_context")
    op.drop_constraint("profile_revision_context_identity", "profile_revision", schema="panestria", type_="unique")
