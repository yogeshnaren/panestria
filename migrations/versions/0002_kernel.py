"""R0 kernel tables. The empty scaffold revision stays 0001_scaffold.

This revision is the domain schema from the database design: scoped foreign keys,
closed states, optimistic versions, and an append-only contract guard. Later
policy, budget, and fleet tables are not created here.
"""

from __future__ import annotations

from alembic import op

revision = "0002_kernel"
down_revision = "0001_scaffold"
branch_labels = None
depends_on = None

_UPGRADE = (
    "CREATE TABLE panestria.principal ("
    " id uuid PRIMARY KEY,"
    " display_name text NOT NULL,"
    " created_at timestamptz NOT NULL DEFAULT now())",
    "CREATE TABLE panestria.project ("
    " id uuid PRIMARY KEY,"
    " owner_id uuid NOT NULL REFERENCES panestria.principal(id),"
    " root_path text,"
    " trust_profile_id text NOT NULL DEFAULT 'SYNTHETIC_DEV',"
    " trust_profile_version integer NOT NULL DEFAULT 1,"
    " created_at timestamptz NOT NULL DEFAULT now(),"
    " UNIQUE (id, owner_id))",
    "CREATE TABLE panestria.goal ("
    " id uuid PRIMARY KEY,"
    " owner_id uuid NOT NULL REFERENCES panestria.principal(id),"
    " project_id uuid NOT NULL REFERENCES panestria.project(id),"
    " intent text NOT NULL,"
    " status text NOT NULL CHECK (status IN ("
    " 'CREATED','ACTIVE','COMPLETED','FAILED','CANCELLED')),"
    " approved_contract_version integer,"
    " created_at timestamptz NOT NULL DEFAULT now(),"
    " updated_at timestamptz NOT NULL DEFAULT now(),"
    " UNIQUE (id, project_id, owner_id),"
    " FOREIGN KEY (project_id, owner_id)"
    " REFERENCES panestria.project(id, owner_id))",
    "CREATE TABLE panestria.goal_contract ("
    " id uuid PRIMARY KEY,"
    " goal_id uuid NOT NULL REFERENCES panestria.goal(id),"
    " version integer NOT NULL CHECK (version > 0),"
    " schema_version integer NOT NULL DEFAULT 1,"
    " body jsonb NOT NULL,"
    " sha256 char(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),"
    " approved_by uuid REFERENCES panestria.principal(id),"
    " approved_at timestamptz,"
    " created_at timestamptz NOT NULL DEFAULT now(),"
    " UNIQUE (goal_id, version),"
    " UNIQUE (id, goal_id))",
    """
    CREATE FUNCTION panestria.forbid_contract_body_change() RETURNS trigger
    LANGUAGE plpgsql AS $fn$
    BEGIN
      IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'contract deletion prohibited';
      END IF;
      IF (NEW.id, NEW.goal_id, NEW.version, NEW.schema_version, NEW.body, NEW.sha256)
         IS DISTINCT FROM
         (OLD.id, OLD.goal_id, OLD.version, OLD.schema_version, OLD.body, OLD.sha256)
      THEN
        RAISE EXCEPTION 'contract revision requires new version';
      END IF;
      IF OLD.approved_at IS NOT NULL
         AND (NEW.approved_at, NEW.approved_by)
             IS DISTINCT FROM (OLD.approved_at, OLD.approved_by)
      THEN
        RAISE EXCEPTION 'approval metadata is immutable';
      END IF;
      RETURN NEW;
    END;
    $fn$
    """,
    "CREATE TRIGGER contract_immutable"
    " BEFORE UPDATE OR DELETE ON panestria.goal_contract"
    " FOR EACH ROW EXECUTE FUNCTION panestria.forbid_contract_body_change()",
    "CREATE TABLE panestria.task ("
    " id uuid PRIMARY KEY,"
    " goal_id uuid NOT NULL REFERENCES panestria.goal(id),"
    " contract_id uuid NOT NULL,"
    " name text NOT NULL,"
    " state text NOT NULL CHECK (state IN ("
    " 'CREATED','VALIDATING','READY','LEASED','RUNNING','WAITING_APPROVAL',"
    " 'VERIFYING','RETRY_WAIT','RECONCILING','CANCELLING','COMPLETED',"
    " 'FAILED','CANCELLED','REJECTED')),"
    " row_version bigint NOT NULL DEFAULT 0 CHECK (row_version >= 0),"
    " priority integer NOT NULL DEFAULT 0,"
    " lease_epoch bigint NOT NULL DEFAULT 0,"
    " continuation_kind text CHECK (continuation_kind IN ('DISPATCH','MERGE','FINALIZE')),"
    " resume_phase text,"
    " created_at timestamptz NOT NULL DEFAULT now(),"
    " updated_at timestamptz NOT NULL DEFAULT now(),"
    " UNIQUE (id, goal_id),"
    " UNIQUE (id, contract_id),"
    " FOREIGN KEY (contract_id, goal_id)"
    " REFERENCES panestria.goal_contract(id, goal_id))",
    "CREATE TABLE panestria.task_dependency ("
    " task_id uuid NOT NULL REFERENCES panestria.task(id),"
    " depends_on uuid NOT NULL REFERENCES panestria.task(id),"
    " PRIMARY KEY (task_id, depends_on),"
    " CHECK (task_id <> depends_on))",
    "CREATE TABLE panestria.task_attempt ("
    " id uuid PRIMARY KEY,"
    " task_id uuid NOT NULL REFERENCES panestria.task(id),"
    " attempt_number integer NOT NULL CHECK (attempt_number > 0),"
    " lease_epoch bigint NOT NULL CHECK (lease_epoch >= 0),"
    " status text NOT NULL CHECK (status IN ("
    " 'PENDING','RUNNING','SUCCEEDED','FAILED','LOST','CANCELLING','CANCELLED')),"
    " adapter text NOT NULL,"
    " external_ref text,"
    " started_at timestamptz,"
    " heartbeat_at timestamptz,"
    " finished_at timestamptz,"
    " error_code text,"
    " UNIQUE (task_id, attempt_number),"
    " UNIQUE (task_id, lease_epoch),"
    " UNIQUE (id, task_id))",
    "CREATE TABLE panestria.workflow_link ("
    " task_id uuid NOT NULL REFERENCES panestria.task(id),"
    " attempt_id uuid NOT NULL,"
    " dbos_workflow_id text NOT NULL UNIQUE,"
    " PRIMARY KEY (task_id, attempt_id),"
    " FOREIGN KEY (attempt_id, task_id)"
    " REFERENCES panestria.task_attempt(id, task_id))",
    "CREATE TABLE panestria.acceptance_check ("
    " id uuid PRIMARY KEY,"
    " contract_id uuid NOT NULL REFERENCES panestria.goal_contract(id),"
    " check_key text NOT NULL,"
    " description text NOT NULL,"
    " verifier_type text NOT NULL CHECK (verifier_type IN ("
    " 'trusted-command-ref','git-diff-path-check','policy-decision',"
    " 'artifact-exists','human-review','citation-check','rubric-review')),"
    " verifier_spec jsonb NOT NULL,"
    " required boolean NOT NULL DEFAULT true,"
    " UNIQUE (contract_id, check_key),"
    " UNIQUE (id, contract_id),"
    " CHECK (jsonb_typeof(verifier_spec) = 'object'"
    " AND verifier_spec ? 'type'"
    " AND verifier_spec->>'type' = verifier_type))",
    "CREATE TABLE panestria.artifact ("
    " id uuid PRIMARY KEY,"
    " task_id uuid NOT NULL REFERENCES panestria.task(id),"
    " attempt_id uuid,"
    " kind text NOT NULL,"
    " store_key text NOT NULL,"
    " sha256 char(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),"
    " privacy_class text NOT NULL DEFAULT 'RESTRICTED',"
    " size_bytes bigint NOT NULL CHECK (size_bytes >= 0),"
    " created_at timestamptz NOT NULL DEFAULT now(),"
    " UNIQUE (id, task_id),"
    " FOREIGN KEY (attempt_id, task_id)"
    " REFERENCES panestria.task_attempt(id, task_id))",
    "CREATE TABLE panestria.check_run ("
    " id uuid PRIMARY KEY,"
    " acceptance_check_id uuid NOT NULL,"
    " attempt_id uuid NOT NULL,"
    " task_id uuid NOT NULL,"
    " contract_id uuid NOT NULL,"
    " verdict text NOT NULL CHECK (verdict IN ('PASS','FAIL','UNKNOWN','ERROR')),"
    " evidence_artifact_id uuid,"
    " checked_at timestamptz NOT NULL DEFAULT now(),"
    " FOREIGN KEY (acceptance_check_id, contract_id)"
    " REFERENCES panestria.acceptance_check(id, contract_id),"
    " FOREIGN KEY (attempt_id, task_id)"
    " REFERENCES panestria.task_attempt(id, task_id),"
    " FOREIGN KEY (task_id, contract_id)"
    " REFERENCES panestria.task(id, contract_id),"
    " FOREIGN KEY (evidence_artifact_id, task_id)"
    " REFERENCES panestria.artifact(id, task_id),"
    " CHECK (verdict <> 'PASS' OR evidence_artifact_id IS NOT NULL))",
    "CREATE TABLE panestria.approval_request ("
    " id uuid PRIMARY KEY,"
    " goal_id uuid NOT NULL,"
    " task_id uuid,"
    " owner_id uuid NOT NULL REFERENCES panestria.principal(id),"
    " project_id uuid NOT NULL REFERENCES panestria.project(id),"
    " minimum_actor_id uuid NOT NULL REFERENCES panestria.principal(id),"
    " action_kind text NOT NULL,"
    " effect_digest char(64) NOT NULL CHECK (effect_digest ~ '^[0-9a-f]{64}$'),"
    " policy_version text NOT NULL,"
    " state text NOT NULL CHECK (state IN ("
    " 'PENDING','APPROVED','DENIED','EXPIRED','REVOKED')),"
    " expires_at timestamptz NOT NULL,"
    " decided_at timestamptz,"
    " decided_by uuid REFERENCES panestria.principal(id),"
    " CHECK (state = 'PENDING' OR state = 'EXPIRED' OR decided_at IS NOT NULL),"
    " FOREIGN KEY (goal_id, project_id, owner_id)"
    " REFERENCES panestria.goal(id, project_id, owner_id),"
    " FOREIGN KEY (task_id, goal_id) REFERENCES panestria.task(id, goal_id))",
    "CREATE TABLE panestria.task_event ("
    " id uuid PRIMARY KEY,"
    " goal_id uuid NOT NULL REFERENCES panestria.goal(id),"
    " task_id uuid,"
    " attempt_id uuid,"
    " seq bigint GENERATED ALWAYS AS IDENTITY (CACHE 1) NOT NULL UNIQUE,"
    " kind text NOT NULL,"
    " occurred_at timestamptz NOT NULL DEFAULT now(),"
    " actor text NOT NULL,"
    " trace_id text,"
    " payload jsonb NOT NULL DEFAULT '{}'::jsonb,"
    " FOREIGN KEY (task_id, goal_id) REFERENCES panestria.task(id, goal_id),"
    " FOREIGN KEY (attempt_id, task_id)"
    " REFERENCES panestria.task_attempt(id, task_id))",
    "CREATE TABLE panestria.side_effect ("
    " id uuid PRIMARY KEY,"
    " task_id uuid NOT NULL REFERENCES panestria.task(id),"
    " effect_key text NOT NULL,"
    " target text NOT NULL,"
    " request_hash char(64) NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),"
    " state text NOT NULL CHECK (state IN ("
    " 'PREPARED','EXECUTING','SUCCEEDED','FAILED','UNKNOWN','RECONCILING')),"
    " external_ref text,"
    " reconciliation_note text,"
    " effect_digest char(64),"
    " approval_request_id uuid REFERENCES panestria.approval_request(id),"
    " UNIQUE (task_id, effect_key))",
    "CREATE TABLE panestria.approval_consumption ("
    " approval_request_id uuid PRIMARY KEY REFERENCES panestria.approval_request(id),"
    " side_effect_id uuid UNIQUE REFERENCES panestria.side_effect(id),"
    " consumed_by uuid NOT NULL REFERENCES panestria.principal(id),"
    " consumed_at timestamptz NOT NULL DEFAULT now(),"
    " effect_digest char(64) NOT NULL CHECK (effect_digest ~ '^[0-9a-f]{64}$'))",
    "CREATE TABLE panestria.idempotency_record ("
    " owner_id uuid NOT NULL REFERENCES panestria.principal(id),"
    " project_id uuid NOT NULL,"
    " operation text NOT NULL,"
    " request_key text NOT NULL,"
    " request_hash char(64) NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),"
    " response_ref jsonb NOT NULL,"
    " created_at timestamptz NOT NULL DEFAULT now(),"
    " PRIMARY KEY (owner_id, project_id, operation, request_key),"
    " FOREIGN KEY (project_id, owner_id) REFERENCES panestria.project(id, owner_id))",
    "CREATE INDEX ix_task_goal ON panestria.task(goal_id)",
    "CREATE INDEX ix_event_goal_seq ON panestria.task_event(goal_id, seq)",
    "CREATE INDEX ix_approvals_owner_pending ON panestria.approval_request(owner_id, state, expires_at)",
)

_DOWNGRADE = (
    "DROP TABLE IF EXISTS"
    " panestria.idempotency_record,"
    " panestria.approval_consumption,"
    " panestria.side_effect,"
    " panestria.task_event,"
    " panestria.approval_request,"
    " panestria.check_run,"
    " panestria.artifact,"
    " panestria.acceptance_check,"
    " panestria.workflow_link,"
    " panestria.task_attempt,"
    " panestria.task_dependency,"
    " panestria.task,"
    " panestria.goal_contract,"
    " panestria.goal,"
    " panestria.project,"
    " panestria.principal CASCADE",
    "DROP FUNCTION IF EXISTS panestria.forbid_contract_body_change()",
)


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
