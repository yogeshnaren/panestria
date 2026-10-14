"""Goal-wide cash reservations; unknown exposure remains reserved."""

from alembic import op

revision = "0007_budgets"
down_revision = "0006_effect_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE panestria.goal_budget (
        goal_id uuid PRIMARY KEY REFERENCES panestria.goal(id),
        cash_cap_microusd bigint CHECK(cash_cap_microusd >= 0),
        settled_microusd bigint NOT NULL DEFAULT 0 CHECK(settled_microusd >= 0),
        row_version bigint NOT NULL DEFAULT 0 CHECK(row_version >= 0))""")
    op.execute("""CREATE TABLE panestria.budget_reservation (
        id uuid PRIMARY KEY,
        goal_id uuid NOT NULL REFERENCES panestria.goal_budget(goal_id),
        task_id uuid NOT NULL,
        request_key text NOT NULL,
        amount_microusd bigint NOT NULL CHECK(amount_microusd >= 0),
        actual_microusd bigint CHECK(actual_microusd >= 0),
        state text NOT NULL CHECK(state IN ('RESERVED','SETTLED','RELEASED','UNKNOWN')),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        UNIQUE(goal_id,request_key),
        FOREIGN KEY(task_id,goal_id) REFERENCES panestria.task(id,goal_id),
        CHECK((state='SETTLED') = (actual_microusd IS NOT NULL)))""")


def downgrade() -> None:
    op.execute("DROP TABLE panestria.budget_reservation,panestria.goal_budget")
