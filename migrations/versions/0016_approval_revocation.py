"""R1 revocation is separate metadata; an original approval decision stays immutable."""

from alembic import op

revision = "0016_approval_revocation"
down_revision = "0015_build_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE panestria.approval_request ADD COLUMN revoked_at timestamptz,"
        " ADD COLUMN revoked_by uuid REFERENCES panestria.principal(id),"
        " ADD COLUMN revocation_policy_version bigint,"
        " ADD CONSTRAINT approval_revocation_policy FOREIGN KEY(project_id,revocation_policy_version)"
        " REFERENCES panestria.project_policy_revision(project_id,version),"
        " ADD CONSTRAINT approval_revocation_metadata CHECK("
        " (revoked_at IS NULL AND revoked_by IS NULL AND revocation_policy_version IS NULL) OR"
        " (state='REVOKED' AND revoked_at IS NOT NULL AND revoked_by=owner_id"
        " AND revoked_by IS NOT NULL AND revocation_policy_version IS NOT NULL"
        " AND revocation_policy_version>0))"
    )
    op.execute("""CREATE OR REPLACE FUNCTION panestria.forbid_approval_rebinding() RETURNS trigger
        LANGUAGE plpgsql AS $fn$
        DECLARE active_version bigint;
        BEGIN
            IF (NEW.id,NEW.goal_id,NEW.task_id,NEW.owner_id,NEW.project_id,NEW.minimum_actor_id,
                NEW.action_kind,NEW.effect_digest,NEW.policy_version,NEW.expires_at,NEW.preview)
                IS DISTINCT FROM
                (OLD.id,OLD.goal_id,OLD.task_id,OLD.owner_id,OLD.project_id,OLD.minimum_actor_id,
                OLD.action_kind,OLD.effect_digest,OLD.policy_version,OLD.expires_at,OLD.preview) THEN
                RAISE EXCEPTION 'approval binding is immutable'; END IF;
            IF OLD.state<>'PENDING' THEN
                IF NEW.state IS DISTINCT FROM OLD.state AND NOT(OLD.state='APPROVED' AND NEW.state='REVOKED') THEN
                    RAISE EXCEPTION 'approval decision is immutable'; END IF;
                IF (NEW.decided_at,NEW.decided_by) IS DISTINCT FROM (OLD.decided_at,OLD.decided_by) THEN
                    RAISE EXCEPTION 'approval decision metadata is immutable'; END IF;
            END IF;
            IF NEW.state='REVOKED' AND OLD.state<>'REVOKED' THEN
                SELECT policy_version INTO active_version FROM panestria.project
                    WHERE id=NEW.project_id AND owner_id=NEW.owner_id;
                IF NEW.revoked_at IS NULL OR NEW.revoked_by IS DISTINCT FROM NEW.owner_id
                    OR NEW.revocation_policy_version IS DISTINCT FROM active_version OR active_version<=0 THEN
                    RAISE EXCEPTION 'approval revocation requires current scoped policy'; END IF;
            ELSIF (NEW.revoked_at,NEW.revoked_by,NEW.revocation_policy_version)
                IS DISTINCT FROM (OLD.revoked_at,OLD.revoked_by,OLD.revocation_policy_version) THEN
                RAISE EXCEPTION 'approval revocation is immutable';
            END IF;
            RETURN NEW;
        END; $fn$""")


def downgrade() -> None:
    op.execute("""CREATE OR REPLACE FUNCTION panestria.forbid_approval_rebinding() RETURNS trigger
        LANGUAGE plpgsql AS $fn$
        BEGIN
            IF (NEW.id,NEW.goal_id,NEW.task_id,NEW.owner_id,NEW.project_id,NEW.minimum_actor_id,
                NEW.action_kind,NEW.effect_digest,NEW.policy_version,NEW.expires_at,NEW.preview)
                IS DISTINCT FROM
                (OLD.id,OLD.goal_id,OLD.task_id,OLD.owner_id,OLD.project_id,OLD.minimum_actor_id,
                OLD.action_kind,OLD.effect_digest,OLD.policy_version,OLD.expires_at,OLD.preview) THEN
                RAISE EXCEPTION 'approval binding is immutable'; END IF;
            IF OLD.state<>'PENDING' AND NEW.state IS DISTINCT FROM OLD.state THEN
                RAISE EXCEPTION 'approval decision is immutable'; END IF;
            RETURN NEW;
        END; $fn$""")
    op.execute(
        "ALTER TABLE panestria.approval_request DROP CONSTRAINT approval_revocation_policy,"
        " DROP CONSTRAINT approval_revocation_metadata, DROP COLUMN revoked_at,"
        " DROP COLUMN revoked_by, DROP COLUMN revocation_policy_version"
    )
