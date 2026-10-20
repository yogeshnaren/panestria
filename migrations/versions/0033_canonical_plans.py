"""Immutable plan/consent/task membership and source-bound handoff records."""

from alembic import op

revision = "0033_canonical_plans"
down_revision = "0032_structured_style"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE panestria.build_plan (
        id uuid PRIMARY KEY, owner_id uuid NOT NULL, project_id uuid NOT NULL, goal_id uuid NOT NULL,
        contract_id uuid NOT NULL, version integer NOT NULL CHECK(version>0), parent_id uuid,
        body jsonb NOT NULL CHECK(jsonb_typeof(body)='object'),
        inventory jsonb NOT NULL CHECK(jsonb_typeof(inventory)='object'),
        validation jsonb NOT NULL CHECK(jsonb_typeof(validation)='object'),
        consent jsonb NOT NULL CHECK(jsonb_typeof(consent)='object'),
        proposal_sha256 char(64) NOT NULL CHECK(proposal_sha256 ~ '^[0-9a-f]{64}$'),
        inventory_sha256 char(64) NOT NULL CHECK(inventory_sha256 ~ '^[0-9a-f]{64}$'),
        effect_digest char(64) NOT NULL CHECK(effect_digest ~ '^[0-9a-f]{64}$'),
        expires_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        UNIQUE(goal_id,version), UNIQUE(id,goal_id,contract_id), UNIQUE(id,goal_id),
        FOREIGN KEY(goal_id,project_id,owner_id) REFERENCES panestria.goal(id,project_id,owner_id),
        FOREIGN KEY(contract_id,goal_id) REFERENCES panestria.goal_contract(id,goal_id),
        FOREIGN KEY(parent_id,goal_id) REFERENCES panestria.build_plan(id,goal_id),
        CHECK((version=1 AND parent_id IS NULL) OR (version>1 AND parent_id IS NOT NULL)),
        CHECK(body->>'plan_id'=id::text AND body->>'goal_id'=goal_id::text
            AND body->>'owner_id'=owner_id::text AND body->>'project_id'=project_id::text))""")
    op.execute("""CREATE TABLE panestria.build_plan_acceptance (
        plan_id uuid PRIMARY KEY, goal_id uuid NOT NULL, contract_id uuid NOT NULL,
        owner_id uuid NOT NULL, project_id uuid NOT NULL, accepted_by uuid NOT NULL CHECK(accepted_by=owner_id),
        effect_digest char(64) NOT NULL CHECK(effect_digest ~ '^[0-9a-f]{64}$'),
        accepted_at timestamptz NOT NULL DEFAULT clock_timestamp(), UNIQUE(plan_id,goal_id,contract_id),
        FOREIGN KEY(plan_id,goal_id,contract_id) REFERENCES panestria.build_plan(id,goal_id,contract_id),
        FOREIGN KEY(goal_id,project_id,owner_id) REFERENCES panestria.goal(id,project_id,owner_id))""")
    op.execute("""CREATE TABLE panestria.build_plan_task (
        plan_id uuid NOT NULL, task_id uuid PRIMARY KEY, goal_id uuid NOT NULL, contract_id uuid NOT NULL,
        node_sha256 char(64) NOT NULL CHECK(node_sha256 ~ '^[0-9a-f]{64}$'),
        UNIQUE(plan_id,task_id),
        FOREIGN KEY(plan_id,goal_id,contract_id)
            REFERENCES panestria.build_plan_acceptance(plan_id,goal_id,contract_id),
        FOREIGN KEY(task_id,goal_id) REFERENCES panestria.task(id,goal_id),
        FOREIGN KEY(task_id,contract_id) REFERENCES panestria.task(id,contract_id))""")
    op.execute("""CREATE TABLE panestria.build_handoff (
        id uuid PRIMARY KEY, plan_id uuid NOT NULL, task_id uuid NOT NULL, attempt_id uuid NOT NULL,
        lease_epoch bigint NOT NULL CHECK(lease_epoch>0), task_version bigint NOT NULL CHECK(task_version>=0),
        body jsonb NOT NULL CHECK(jsonb_typeof(body)='object'),
        sha256 char(64) NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        UNIQUE(task_id,attempt_id,lease_epoch),
        FOREIGN KEY(plan_id,task_id) REFERENCES panestria.build_plan_task(plan_id,task_id),
        FOREIGN KEY(attempt_id,task_id) REFERENCES panestria.task_attempt(id,task_id))""")
    for table in ("build_plan", "build_plan_acceptance", "build_plan_task", "build_handoff"):
        op.execute(
            f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON panestria.{table} "
            "FOR EACH ROW EXECUTE FUNCTION panestria.immutable_memory_record()"
        )


def downgrade() -> None:
    op.execute("LOCK TABLE panestria.build_plan IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().exec_driver_sql("SELECT EXISTS(SELECT 1 FROM panestria.build_plan)").scalar():
        raise RuntimeError("canonical plan audit exists; restore or forward repair required")
    for table in ("build_handoff", "build_plan_task", "build_plan_acceptance", "build_plan"):
        op.execute(f"DROP TABLE panestria.{table}")
