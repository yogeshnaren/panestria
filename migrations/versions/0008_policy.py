"""Immutable policy revisions and owner-reviewed project changes."""

from alembic import op

revision = "0008_policy"
down_revision = "0007_budgets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE panestria.project ADD COLUMN policy_version bigint NOT NULL DEFAULT 0 CHECK(policy_version>=0)"
    )
    op.execute("""CREATE TABLE panestria.project_policy_revision (
        project_id uuid NOT NULL, owner_id uuid NOT NULL,
        version bigint NOT NULL CHECK(version>0),
        trust_version bigint NOT NULL CHECK(trust_version>0),
        privacy_version bigint NOT NULL CHECK(privacy_version>0),
        autonomy_version bigint NOT NULL CHECK(autonomy_version>0),
        body jsonb NOT NULL, sha256 char(64) NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        PRIMARY KEY(project_id,version),
        FOREIGN KEY(project_id,owner_id) REFERENCES panestria.project(id,owner_id))""")
    op.execute("""CREATE TABLE panestria.policy_review (
        id uuid PRIMARY KEY, project_id uuid NOT NULL, owner_id uuid NOT NULL,
        task_id uuid NOT NULL REFERENCES panestria.task(id),
        expected_version bigint NOT NULL CHECK(expected_version>0),
        effect_digest char(64) NOT NULL CHECK(effect_digest ~ '^[0-9a-f]{64}$'),
        proposed_body jsonb NOT NULL,
        state text NOT NULL CHECK(state IN ('PENDING','APPROVED','DENIED','APPLIED')),
        expires_at timestamptz NOT NULL, decided_at timestamptz,
        decided_by uuid REFERENCES panestria.principal(id),
        FOREIGN KEY(project_id,owner_id) REFERENCES panestria.project(id,owner_id),
        CHECK(state='PENDING' OR decided_at IS NOT NULL))""")
    op.execute("""CREATE FUNCTION panestria.immutable_policy_revision() RETURNS trigger LANGUAGE plpgsql AS $fn$
        BEGIN RAISE EXCEPTION 'policy revision is immutable'; END; $fn$""")
    op.execute(
        "CREATE TRIGGER immutable_revision BEFORE UPDATE OR DELETE ON panestria.project_policy_revision"
        " FOR EACH ROW EXECUTE FUNCTION panestria.immutable_policy_revision()"
    )

    op.execute("""CREATE FUNCTION panestria.immutable_policy_review() RETURNS trigger LANGUAGE plpgsql AS $fn$
        BEGIN
          IF (NEW.id,NEW.project_id,NEW.owner_id,NEW.task_id,NEW.expected_version,
              NEW.effect_digest,NEW.proposed_body,NEW.expires_at) IS DISTINCT FROM
             (OLD.id,OLD.project_id,OLD.owner_id,OLD.task_id,OLD.expected_version,
              OLD.effect_digest,OLD.proposed_body,OLD.expires_at) THEN
            RAISE EXCEPTION 'policy review fingerprint is immutable';
          END IF;
          IF OLD.state IN ('DENIED','APPLIED') AND NEW IS DISTINCT FROM OLD THEN
            RAISE EXCEPTION 'policy review decision is terminal';
          END IF;
          RETURN NEW;
        END; $fn$""")
    op.execute(
        "CREATE TRIGGER immutable_review BEFORE UPDATE ON panestria.policy_review"
        " FOR EACH ROW EXECUTE FUNCTION panestria.immutable_policy_review()"
    )


def downgrade() -> None:
    op.execute("DROP TABLE panestria.policy_review,panestria.project_policy_revision")
    op.execute("DROP FUNCTION panestria.immutable_policy_revision(),panestria.immutable_policy_review()")
    op.execute("ALTER TABLE panestria.project DROP COLUMN policy_version")
