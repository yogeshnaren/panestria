"""Durable bounded plan-worker reservations; expiry is not process termination."""

from alembic import op

revision = "0034_build_admission"
down_revision = "0033_canonical_plans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE panestria.build_handoff ADD CONSTRAINT build_handoff_claim_ref "
        "UNIQUE(id,task_id,attempt_id,lease_epoch)"
    )
    op.execute("""CREATE TABLE panestria.build_worker_claim (
        attempt_id uuid PRIMARY KEY, plan_id uuid NOT NULL, task_id uuid NOT NULL,
        lease_epoch bigint NOT NULL CHECK(lease_epoch>0), worker_ref text NOT NULL,
        hardware jsonb NOT NULL CHECK(jsonb_typeof(hardware)='object'),
        hardware_sha256 char(64) NOT NULL CHECK(hardware_sha256 ~ '^[0-9a-f]{64}$'),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        released_at timestamptz, handoff_id uuid,
        FOREIGN KEY(handoff_id,task_id,attempt_id,lease_epoch)
            REFERENCES panestria.build_handoff(id,task_id,attempt_id,lease_epoch),
        FOREIGN KEY(plan_id,task_id) REFERENCES panestria.build_plan_task(plan_id,task_id),
        FOREIGN KEY(attempt_id,task_id) REFERENCES panestria.task_attempt(id,task_id),
        CHECK((released_at IS NULL AND handoff_id IS NULL) OR
              (released_at IS NOT NULL AND handoff_id IS NOT NULL)))""")
    op.execute("""CREATE UNIQUE INDEX build_worker_claim_active_task
        ON panestria.build_worker_claim(task_id) WHERE released_at IS NULL""")
    op.execute("""CREATE FUNCTION panestria.guard_build_claim() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP='DELETE' THEN RAISE EXCEPTION 'build claim audit is immutable'; END IF;
          IF OLD.released_at IS NOT NULL OR NEW.released_at IS NULL OR NEW.handoff_id IS NULL OR
            (to_jsonb(NEW)-'released_at'-'handoff_id') IS DISTINCT FROM
            (to_jsonb(OLD)-'released_at'-'handoff_id')
          THEN RAISE EXCEPTION 'only one confirmed claim release is allowed'; END IF;
          RETURN NEW;
        END $$""")
    op.execute("""CREATE TRIGGER guarded_build_worker_claim BEFORE UPDATE OR DELETE
        ON panestria.build_worker_claim FOR EACH ROW EXECUTE FUNCTION panestria.guard_build_claim()""")


def downgrade() -> None:
    op.execute("LOCK TABLE panestria.build_worker_claim IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().exec_driver_sql("SELECT EXISTS(SELECT 1 FROM panestria.build_worker_claim)").scalar():
        raise RuntimeError("build claim audit exists; restore or forward repair required")
    op.execute("DROP TABLE panestria.build_worker_claim")
    op.execute("DROP FUNCTION panestria.guard_build_claim()")
    op.execute("ALTER TABLE panestria.build_handoff DROP CONSTRAINT build_handoff_claim_ref")
