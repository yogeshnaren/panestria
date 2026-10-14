"""Store the canonical approval preview and keep its binding immutable."""

from __future__ import annotations

from alembic import op

revision = "0003_approval_preview"
down_revision = "0002_kernel"
branch_labels = None
depends_on = None

_UPGRADE = (
    "ALTER TABLE panestria.approval_request ADD COLUMN preview jsonb NOT NULL",
    "ALTER TABLE panestria.approval_request"
    " ADD CONSTRAINT approval_preview_object CHECK (jsonb_typeof(preview) = 'object')",
    """
    CREATE FUNCTION panestria.forbid_approval_rebinding() RETURNS trigger
    LANGUAGE plpgsql AS $fn$
    BEGIN
      IF (NEW.id, NEW.goal_id, NEW.task_id, NEW.owner_id, NEW.project_id,
          NEW.minimum_actor_id, NEW.action_kind, NEW.effect_digest,
          NEW.policy_version, NEW.expires_at, NEW.preview)
         IS DISTINCT FROM
         (OLD.id, OLD.goal_id, OLD.task_id, OLD.owner_id, OLD.project_id,
          OLD.minimum_actor_id, OLD.action_kind, OLD.effect_digest,
          OLD.policy_version, OLD.expires_at, OLD.preview)
      THEN
        RAISE EXCEPTION 'approval binding is immutable';
      END IF;
      IF OLD.state <> 'PENDING' AND NEW.state IS DISTINCT FROM OLD.state THEN
        RAISE EXCEPTION 'approval decision is immutable';
      END IF;
      RETURN NEW;
    END;
    $fn$
    """,
    "CREATE TRIGGER approval_binding_immutable"
    " BEFORE UPDATE ON panestria.approval_request"
    " FOR EACH ROW EXECUTE FUNCTION panestria.forbid_approval_rebinding()",
)

_DOWNGRADE = (
    "DROP TRIGGER IF EXISTS approval_binding_immutable ON panestria.approval_request",
    "DROP FUNCTION IF EXISTS panestria.forbid_approval_rebinding()",
    "ALTER TABLE panestria.approval_request DROP COLUMN IF EXISTS preview",
)


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
