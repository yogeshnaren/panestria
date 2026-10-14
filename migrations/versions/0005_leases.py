"""R1 DB-clock leases and stale attempt publication guards."""

from alembic import op

revision = "0005_leases"
down_revision = "0004_check_candidate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE panestria.task ADD COLUMN max_attempts integer NOT NULL DEFAULT 3"
        " CHECK (max_attempts BETWEEN 1 AND 20)"
    )
    op.execute("ALTER TABLE panestria.task ADD COLUMN retry_at timestamptz")
    op.execute("ALTER TABLE panestria.task_attempt ADD COLUMN lease_expires_at timestamptz")
    op.execute(
        "CREATE INDEX ix_attempt_expiry ON panestria.task_attempt(lease_expires_at)"
        " WHERE status IN ('PENDING','RUNNING')"
    )
    op.execute("""
        CREATE FUNCTION panestria.fence_leased_publication() RETURNS trigger LANGUAGE plpgsql AS $fn$
        DECLARE a record; current_epoch bigint;
        BEGIN
          IF NEW.attempt_id IS NULL THEN RETURN NEW; END IF;
          SELECT lease_epoch INTO current_epoch FROM panestria.task WHERE id = NEW.task_id FOR UPDATE;
          SELECT * INTO a FROM panestria.task_attempt WHERE id = NEW.attempt_id AND task_id = NEW.task_id;
          IF a.lease_expires_at IS NOT NULL AND
             (a.lease_epoch <> current_epoch OR a.lease_expires_at <= clock_timestamp()
              OR a.status NOT IN ('PENDING','RUNNING')) THEN
            RAISE EXCEPTION 'stale attempt publication';
          END IF;
          RETURN NEW;
        END; $fn$
    """)
    for table in ("artifact", "check_run"):
        op.execute(
            f"CREATE TRIGGER leased_publication BEFORE INSERT OR UPDATE ON panestria.{table}"
            " FOR EACH ROW EXECUTE FUNCTION panestria.fence_leased_publication()"
        )


def downgrade() -> None:
    for table in ("artifact", "check_run"):
        op.execute(f"DROP TRIGGER leased_publication ON panestria.{table}")
    op.execute("DROP FUNCTION panestria.fence_leased_publication()")
    op.execute("DROP INDEX panestria.ix_attempt_expiry")
    op.execute("ALTER TABLE panestria.task_attempt DROP COLUMN lease_expires_at")
    op.execute("ALTER TABLE panestria.task DROP COLUMN retry_at, DROP COLUMN max_attempts")
