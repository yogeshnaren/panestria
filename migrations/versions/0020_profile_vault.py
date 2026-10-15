"""Separate encrypted profiles from plaintext general-memory/FTS tables."""

from alembic import op

revision = "0020_profile_vault"
down_revision = "0019_canonical_labels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE panestria.profile (
        id uuid PRIMARY KEY, owner_id uuid NOT NULL, project_id uuid NOT NULL,
        current_revision integer NOT NULL DEFAULT 1 CHECK(current_revision BETWEEN 1 AND 1024),
        row_version integer NOT NULL DEFAULT 0 CHECK(row_version>=0),
        status text NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','SUPPRESSED')),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        UNIQUE(id,owner_id,project_id),
        FOREIGN KEY(project_id,owner_id) REFERENCES panestria.project(id,owner_id))""")
    op.execute("""CREATE TABLE panestria.profile_revision (
        id uuid PRIMARY KEY, profile_id uuid NOT NULL, owner_id uuid NOT NULL, project_id uuid NOT NULL,
        version integer NOT NULL CHECK(version BETWEEN 1 AND 1024),
        key_id uuid NOT NULL, schema_version integer NOT NULL CHECK(schema_version=1),
        algorithm text NOT NULL CHECK(algorithm='A256GCM'),
        privacy_label text NOT NULL CHECK(privacy_label='RESTRICTED'),
        nonce bytea NOT NULL CHECK(octet_length(nonce)=12),
        ciphertext bytea NOT NULL CHECK(octet_length(ciphertext) BETWEEN 17 AND 32784),
        ciphertext_sha256 char(64) NOT NULL CHECK(ciphertext_sha256 ~ '^[0-9a-f]{64}$'),
        consented_by uuid NOT NULL CHECK(consented_by=owner_id), consent_ref uuid NOT NULL,
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        UNIQUE(profile_id,owner_id,project_id,version),
        UNIQUE(owner_id,project_id,profile_id,key_id,nonce),
        FOREIGN KEY(profile_id,owner_id,project_id) REFERENCES panestria.profile(id,owner_id,project_id))""")
    op.execute("""ALTER TABLE panestria.profile ADD CONSTRAINT profile_current_revision_fk
        FOREIGN KEY(id,owner_id,project_id,current_revision)
        REFERENCES panestria.profile_revision(profile_id,owner_id,project_id,version)
        DEFERRABLE INITIALLY DEFERRED""")
    op.execute("""CREATE TABLE panestria.profile_event (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        profile_id uuid NOT NULL, owner_id uuid NOT NULL, project_id uuid NOT NULL,
        row_version integer NOT NULL, current_revision integer NOT NULL,
        kind text NOT NULL CHECK(kind IN ('CREATED','REVISED','SUPPRESSED')),
        status text NOT NULL CHECK(status IN ('ACTIVE','SUPPRESSED')),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        UNIQUE(profile_id,row_version),
        FOREIGN KEY(profile_id,owner_id,project_id,current_revision)
            REFERENCES panestria.profile_revision(profile_id,owner_id,project_id,version)
            DEFERRABLE INITIALLY DEFERRED)""")
    op.execute("""CREATE FUNCTION panestria.record_profile_event() RETURNS trigger LANGUAGE plpgsql AS $fn$
        DECLARE event_kind text;
        BEGIN
            IF TG_OP='INSERT' THEN
                IF NEW.current_revision<>1 OR NEW.row_version<>0 OR NEW.status<>'ACTIVE' THEN
                    RAISE EXCEPTION 'profile_initial_state_invalid';
                END IF;
                event_kind:='CREATED';
            ELSE
                IF (NEW.id,NEW.owner_id,NEW.project_id,NEW.created_at) IS DISTINCT FROM
                    (OLD.id,OLD.owner_id,OLD.project_id,OLD.created_at) OR NEW.row_version<>OLD.row_version+1 THEN
                    RAISE EXCEPTION 'profile_transition_invalid';
                END IF;
                IF NEW.current_revision=OLD.current_revision+1 AND NEW.status='ACTIVE' THEN
                    event_kind:='REVISED';
                ELSIF NEW.current_revision=OLD.current_revision AND NEW.status='SUPPRESSED' AND OLD.status='ACTIVE' THEN
                    event_kind:='SUPPRESSED';
                ELSE RAISE EXCEPTION 'profile_transition_invalid'; END IF;
            END IF;
            INSERT INTO panestria.profile_event
                (profile_id,owner_id,project_id,row_version,current_revision,kind,status)
                VALUES(NEW.id,NEW.owner_id,NEW.project_id,NEW.row_version,NEW.current_revision,event_kind,NEW.status);
            RETURN NEW;
        END; $fn$""")
    op.execute("""CREATE TRIGGER profile_lifecycle AFTER INSERT OR UPDATE ON panestria.profile
        FOR EACH ROW EXECUTE FUNCTION panestria.record_profile_event()""")
    for table in ("profile_revision", "profile_event"):
        op.execute(
            f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON panestria.{table}"
            " FOR EACH ROW EXECUTE FUNCTION panestria.immutable_memory_record()"
        )


def downgrade() -> None:
    op.execute("LOCK TABLE panestria.profile IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().exec_driver_sql("SELECT EXISTS(SELECT 1 FROM panestria.profile)").scalar():
        raise RuntimeError("profile audit exists; use forward repair or a reviewed backup")
    op.execute("DROP TRIGGER profile_lifecycle ON panestria.profile")
    op.execute("DROP FUNCTION panestria.record_profile_event()")
    op.execute("ALTER TABLE panestria.profile DROP CONSTRAINT profile_current_revision_fk")
    op.execute("DROP TABLE panestria.profile_event")
    op.execute("DROP TABLE panestria.profile_revision")
    op.execute("DROP TABLE panestria.profile")
