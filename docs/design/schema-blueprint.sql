-- DESIGN ONLY: split and test with Alembic; no runtime execution here.
CREATE SCHEMA IF NOT EXISTS panestria;
SET search_path TO panestria, public;

CREATE TABLE principal (
  id uuid PRIMARY KEY, display_name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE project (
  id uuid PRIMARY KEY, owner_id uuid NOT NULL REFERENCES principal(id),
  root_path text, trust_profile_id text NOT NULL DEFAULT 'SYNTHETIC_DEV',
  trust_profile_version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id,owner_id)
);
CREATE TABLE goal (
  id uuid PRIMARY KEY, owner_id uuid NOT NULL REFERENCES principal(id),
  project_id uuid NOT NULL REFERENCES project(id), intent text NOT NULL,
  status text NOT NULL CHECK (status IN ('CREATED','ACTIVE','COMPLETED','FAILED','CANCELLED')),
  approved_contract_version integer,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id,project_id,owner_id),
  FOREIGN KEY (project_id,owner_id) REFERENCES project(id,owner_id)
);
CREATE TABLE goal_contract (
  id uuid PRIMARY KEY, goal_id uuid NOT NULL REFERENCES goal(id),
  version integer NOT NULL CHECK (version > 0),
  schema_version integer NOT NULL DEFAULT 1,
  body jsonb NOT NULL, sha256 char(64) NOT NULL,
  approved_by uuid REFERENCES principal(id), approved_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (goal_id,version)
);
CREATE TABLE task (
  id uuid PRIMARY KEY, goal_id uuid NOT NULL REFERENCES goal(id),
  contract_id uuid NOT NULL REFERENCES goal_contract(id),
  name text NOT NULL, state text NOT NULL CHECK (state IN ('CREATED','VALIDATING','READY','LEASED','RUNNING','WAITING_APPROVAL','VERIFYING','RETRY_WAIT','RECONCILING','CANCELLING','COMPLETED','FAILED','CANCELLED','REJECTED')),
  row_version bigint NOT NULL DEFAULT 0 CHECK (row_version >= 0),
  priority integer NOT NULL DEFAULT 0, lease_epoch bigint NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(id,goal_id)
);
CREATE TABLE task_dependency (
  task_id uuid NOT NULL REFERENCES task(id), depends_on uuid NOT NULL REFERENCES task(id),
  PRIMARY KEY(task_id,depends_on), CHECK (task_id <> depends_on)
);
CREATE TABLE task_attempt (
  id uuid PRIMARY KEY, task_id uuid NOT NULL REFERENCES task(id),
  attempt_number integer NOT NULL, lease_epoch bigint NOT NULL,
  status text NOT NULL, adapter text NOT NULL, external_ref text,
  started_at timestamptz, heartbeat_at timestamptz, finished_at timestamptz,
  error_code text, UNIQUE(task_id,attempt_number), UNIQUE(task_id,lease_epoch)
);
CREATE TABLE workflow_link (
  task_id uuid NOT NULL REFERENCES task(id), attempt_id uuid NOT NULL REFERENCES task_attempt(id),
  dbos_workflow_id text NOT NULL UNIQUE, PRIMARY KEY(task_id,attempt_id)
);
CREATE TABLE acceptance_check (
  id uuid PRIMARY KEY, contract_id uuid NOT NULL REFERENCES goal_contract(id),
  check_key text NOT NULL, description text NOT NULL,
  verifier_type text NOT NULL CHECK (verifier_type IN ('trusted-command-ref','git-diff-path-check','policy-decision','artifact-exists','human-review','citation-check','rubric-review')),
  verifier_spec jsonb NOT NULL,
  required boolean NOT NULL DEFAULT true, UNIQUE(contract_id,check_key),
  CHECK (jsonb_typeof(verifier_spec)='object' AND verifier_spec ? 'type' AND verifier_spec->>'type'=verifier_type)
);
CREATE TABLE check_run (
  id uuid PRIMARY KEY, acceptance_check_id uuid NOT NULL REFERENCES acceptance_check(id),
  attempt_id uuid NOT NULL REFERENCES task_attempt(id),
  verdict text NOT NULL CHECK (verdict IN ('PASS','FAIL','UNKNOWN','ERROR')),
  evidence_artifact_id uuid, checked_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE artifact (
  id uuid PRIMARY KEY, task_id uuid NOT NULL REFERENCES task(id), attempt_id uuid REFERENCES task_attempt(id),
  kind text NOT NULL, store_key text NOT NULL, sha256 char(64) NOT NULL,
  privacy_class text NOT NULL DEFAULT 'RESTRICTED', size_bytes bigint NOT NULL CHECK(size_bytes >= 0),
  created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE check_run ADD CONSTRAINT check_run_artifact_fk FOREIGN KEY(evidence_artifact_id) REFERENCES artifact(id);
CREATE TABLE approval_request (
  id uuid PRIMARY KEY, goal_id uuid NOT NULL REFERENCES goal(id), task_id uuid REFERENCES task(id),
  owner_id uuid NOT NULL REFERENCES principal(id),
  project_id uuid NOT NULL REFERENCES project(id),
  minimum_actor_id uuid NOT NULL REFERENCES principal(id), action_kind text NOT NULL,
  effect_digest char(64) NOT NULL CHECK (effect_digest ~ '^[0-9a-f]{64}$'), policy_version text NOT NULL,
  state text NOT NULL CHECK(state IN ('PENDING','APPROVED','DENIED','EXPIRED','REVOKED')),
  expires_at timestamptz NOT NULL, decided_at timestamptz, decided_by uuid REFERENCES principal(id),
  CHECK ((state='PENDING') OR (state='EXPIRED') OR (decided_at IS NOT NULL)),
  FOREIGN KEY(goal_id,project_id,owner_id) REFERENCES goal(id,project_id,owner_id),
  FOREIGN KEY(task_id,goal_id) REFERENCES task(id,goal_id)
);
CREATE TABLE task_event (
  id uuid PRIMARY KEY, goal_id uuid NOT NULL REFERENCES goal(id), task_id uuid REFERENCES task(id),
  attempt_id uuid REFERENCES task_attempt(id),
  seq bigint GENERATED ALWAYS AS IDENTITY (CACHE 1) NOT NULL UNIQUE,
  kind text NOT NULL, occurred_at timestamptz NOT NULL DEFAULT now(),
  actor text NOT NULL, trace_id text, payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  FOREIGN KEY(task_id,goal_id) REFERENCES task(id,goal_id)
);
CREATE TABLE side_effect (
  id uuid PRIMARY KEY, task_id uuid NOT NULL REFERENCES task(id),
  effect_key text NOT NULL, target text NOT NULL, request_hash char(64) NOT NULL,
  state text NOT NULL CHECK(state IN ('PREPARED','EXECUTING','SUCCEEDED','FAILED','UNKNOWN','RECONCILING')),
  external_ref text, reconciliation_note text,
  UNIQUE(task_id,effect_key)
);
CREATE INDEX ix_task_goal ON task(goal_id);
CREATE INDEX ix_event_goal_seq ON task_event(goal_id,seq);
CREATE INDEX ix_approvals_owner_pending ON approval_request(owner_id,state,expires_at);

-- R0 additional integrity. Assemble with repaired base tables in one new migration.
ALTER TABLE goal_contract ADD CONSTRAINT uq_contract_goal UNIQUE(id,goal_id);
ALTER TABLE task ADD CONSTRAINT fk_task_contract_goal FOREIGN KEY(contract_id,goal_id) REFERENCES goal_contract(id,goal_id);
ALTER TABLE task ADD CONSTRAINT uq_task_contract UNIQUE(id,contract_id);
ALTER TABLE task ADD COLUMN continuation_kind text CHECK(continuation_kind IN ('DISPATCH','MERGE','FINALIZE'));
ALTER TABLE task ADD COLUMN resume_phase text;
ALTER TABLE task_attempt ADD CONSTRAINT uq_attempt_task UNIQUE(id,task_id);
ALTER TABLE task_attempt ADD CONSTRAINT ck_attempt_number CHECK(attempt_number>0);
ALTER TABLE task_attempt ADD CONSTRAINT ck_attempt_epoch CHECK(lease_epoch>=0);
ALTER TABLE workflow_link ADD CONSTRAINT fk_workflow_attempt_task FOREIGN KEY(attempt_id,task_id) REFERENCES task_attempt(id,task_id);
ALTER TABLE artifact ADD CONSTRAINT uq_artifact_task UNIQUE(id,task_id);
ALTER TABLE artifact ADD CONSTRAINT fk_artifact_attempt_task FOREIGN KEY(attempt_id,task_id) REFERENCES task_attempt(id,task_id);
ALTER TABLE acceptance_check ADD CONSTRAINT uq_check_contract UNIQUE(id,contract_id);
ALTER TABLE acceptance_check ADD CONSTRAINT ck_verifier_type_nonnull CHECK(verifier_spec->>'type' IS NOT NULL);
ALTER TABLE check_run ADD COLUMN task_id uuid NOT NULL REFERENCES task(id);
ALTER TABLE check_run ADD COLUMN contract_id uuid NOT NULL REFERENCES goal_contract(id);
ALTER TABLE check_run ADD CONSTRAINT fk_run_check_contract FOREIGN KEY(acceptance_check_id,contract_id) REFERENCES acceptance_check(id,contract_id);
ALTER TABLE check_run ADD CONSTRAINT fk_run_task_contract FOREIGN KEY(task_id,contract_id) REFERENCES task(id,contract_id);
ALTER TABLE check_run ADD CONSTRAINT fk_run_attempt_task FOREIGN KEY(attempt_id,task_id) REFERENCES task_attempt(id,task_id);
ALTER TABLE check_run ADD CONSTRAINT fk_run_artifact_task FOREIGN KEY(evidence_artifact_id,task_id) REFERENCES artifact(id,task_id);
ALTER TABLE check_run ADD CONSTRAINT ck_pass_evidence CHECK(verdict<>'PASS' OR evidence_artifact_id IS NOT NULL);
ALTER TABLE task_event ADD CONSTRAINT fk_event_attempt_task FOREIGN KEY(attempt_id,task_id) REFERENCES task_attempt(id,task_id);
ALTER TABLE side_effect ADD COLUMN effect_digest char(64);
ALTER TABLE side_effect ADD COLUMN approval_request_id uuid REFERENCES approval_request(id);
CREATE TABLE approval_consumption (
 approval_request_id uuid PRIMARY KEY REFERENCES approval_request(id),
 side_effect_id uuid UNIQUE REFERENCES side_effect(id),
 consumed_by uuid NOT NULL REFERENCES principal(id), consumed_at timestamptz NOT NULL DEFAULT now(),
 effect_digest char(64) NOT NULL
);
CREATE TABLE idempotency_record (
 owner_id uuid NOT NULL REFERENCES principal(id), project_id uuid NOT NULL REFERENCES project(id),
 operation text NOT NULL, request_key text NOT NULL, request_hash char(64) NOT NULL,
 response_ref jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(owner_id,project_id,operation,request_key),
 FOREIGN KEY(project_id,owner_id) REFERENCES project(id,owner_id)
);
CREATE FUNCTION forbid_contract_body_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'contract deletion prohibited'; END IF;
 IF (NEW.id,NEW.goal_id,NEW.version,NEW.schema_version,NEW.body,NEW.sha256)
 IS DISTINCT FROM (OLD.id,OLD.goal_id,OLD.version,OLD.schema_version,OLD.body,OLD.sha256)
 THEN RAISE EXCEPTION 'contract revision requires new version'; END IF;
 IF OLD.approved_at IS NOT NULL AND (NEW.approved_at,NEW.approved_by) IS DISTINCT FROM (OLD.approved_at,OLD.approved_by)
 THEN RAISE EXCEPTION 'approval metadata is immutable'; END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER contract_immutable BEFORE UPDATE OR DELETE ON goal_contract FOR EACH ROW EXECUTE FUNCTION forbid_contract_body_change();

-- 0002_policy_effects: harden existing R0 effect/consumption primitives.
ALTER TABLE task_attempt ADD COLUMN lease_expires_at timestamptz;
ALTER TABLE task_attempt ADD COLUMN adapter_version text;
ALTER TABLE task_attempt ADD COLUMN process_receipt jsonb;
ALTER TABLE task_attempt ADD CONSTRAINT ck_attempt_status CHECK(status IN ('PENDING','RUNNING','SUCCEEDED','FAILED','LOST','CANCELLING','CANCELLED'));
ALTER TABLE side_effect ADD COLUMN attempt_id uuid REFERENCES task_attempt(id);
ALTER TABLE side_effect ADD COLUMN classification text CHECK(classification IN ('READ_ONLY','IDEMPOTENT_KEY','RECONCILE_QUERY','COMPENSATABLE','NON_RETRYABLE'));
ALTER TABLE side_effect ADD COLUMN receipt_artifact_id uuid REFERENCES artifact(id);
ALTER TABLE side_effect ADD CONSTRAINT fk_effect_attempt_task FOREIGN KEY(attempt_id,task_id) REFERENCES task_attempt(id,task_id);
CREATE TABLE outbox_intent (
 id uuid PRIMARY KEY, side_effect_id uuid NOT NULL UNIQUE REFERENCES side_effect(id),
 state text NOT NULL CHECK(state IN ('PENDING','CLAIMED','CONFIRMED','UNKNOWN','FAILED')),
 dispatch_epoch bigint NOT NULL DEFAULT 0, next_attempt_at timestamptz,
 attempts integer NOT NULL DEFAULT 0 CHECK(attempts>=0), receipt_ref jsonb
);
CREATE TABLE project_budget (
 project_id uuid PRIMARY KEY REFERENCES project(id), owner_id uuid NOT NULL REFERENCES principal(id),
 api_cap_microusd bigint NOT NULL DEFAULT 0 CHECK(api_cap_microusd>=0),
 settled_microusd bigint NOT NULL DEFAULT 0 CHECK(settled_microusd>=0), revision bigint NOT NULL DEFAULT 0,
 FOREIGN KEY(project_id,owner_id) REFERENCES project(id,owner_id)
);
CREATE TABLE budget_reservation (
 id uuid PRIMARY KEY, project_id uuid NOT NULL REFERENCES project_budget(project_id), task_id uuid NOT NULL REFERENCES task(id),
 attempt_id uuid NOT NULL REFERENCES task_attempt(id), reserved_microusd bigint NOT NULL CHECK(reserved_microusd>=0),
 state text NOT NULL CHECK(state IN ('RESERVED','SETTLED','RELEASED','UNKNOWN')),
 settled_microusd bigint CHECK(settled_microusd>=0), UNIQUE(attempt_id),
 FOREIGN KEY(attempt_id,task_id) REFERENCES task_attempt(id,task_id)
);
CREATE TABLE project_trust_profile (
 project_id uuid NOT NULL REFERENCES project(id), version integer NOT NULL CHECK(version>0),
 profile_id text NOT NULL, certified_gate_ref jsonb NOT NULL, changed_by uuid NOT NULL REFERENCES principal(id),
 PRIMARY KEY(project_id,version)
);
CREATE TABLE project_action_policy (
 project_id uuid NOT NULL REFERENCES project(id), version integer NOT NULL CHECK(version>0),
 action text NOT NULL, autonomy text NOT NULL CHECK(autonomy IN ('OBSERVE','SUGGEST','APPROVE_FIRST','ACT_AND_REPORT','ACT_SILENTLY')),
 changed_by uuid NOT NULL REFERENCES principal(id), PRIMARY KEY(project_id,version,action)
);
CREATE TABLE policy_decision (
 id uuid PRIMARY KEY, owner_id uuid NOT NULL REFERENCES principal(id), project_id uuid NOT NULL REFERENCES project(id),
 task_id uuid REFERENCES task(id), attempt_id uuid REFERENCES task_attempt(id),
 verdict text NOT NULL CHECK(verdict IN ('PERMIT','DENY','APPROVAL_NEEDED')),
 policy_version text NOT NULL, request_hash char(64) NOT NULL, reasons jsonb NOT NULL,
 enforcement_manifest jsonb NOT NULL, expires_at timestamptz,
 FOREIGN KEY(project_id,owner_id) REFERENCES project(id,owner_id)
);
CREATE TABLE capability_manifest (
 id uuid PRIMARY KEY, capability_id text NOT NULL, version text NOT NULL, sha256 char(64) NOT NULL,
 permissions jsonb NOT NULL, compatibility jsonb NOT NULL,
 review_status text NOT NULL CHECK(review_status IN ('CANDIDATE','APPROVED','REVOKED')), UNIQUE(capability_id,version)
);
CREATE TABLE sandbox_run (
 id uuid PRIMARY KEY, attempt_id uuid NOT NULL REFERENCES task_attempt(id), profile_id text NOT NULL, profile_version text NOT NULL,
 effective_manifest jsonb NOT NULL, sha256 char(64) NOT NULL,
 state text NOT NULL CHECK(state IN ('CREATED','RUNNING','STOPPED','UNKNOWN','FAILED'))
);
CREATE TABLE local_session (
 id uuid PRIMARY KEY, owner_id uuid NOT NULL REFERENCES principal(id), token_hash char(64) NOT NULL UNIQUE,
 expires_at timestamptz NOT NULL, revoked_at timestamptz, kind text NOT NULL CHECK(kind IN ('CLI','BROWSER','PAIRING'))
);

-- 0003_memory
CREATE TABLE memory_source (
 id uuid PRIMARY KEY, owner_id uuid NOT NULL REFERENCES principal(id), project_id uuid NOT NULL REFERENCES project(id),
 source_ref text NOT NULL, sha256 char(64) NOT NULL, privacy_class text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(id,project_id,owner_id),
 FOREIGN KEY(project_id,owner_id) REFERENCES project(id,owner_id)
);
CREATE TABLE memory_item (
 id uuid PRIMARY KEY, owner_id uuid NOT NULL REFERENCES principal(id), project_id uuid NOT NULL REFERENCES project(id),
 kind text NOT NULL, current_revision integer NOT NULL CHECK(current_revision>0),
 pinned boolean NOT NULL DEFAULT false, suppressed_at timestamptz, retention_until timestamptz,
 UNIQUE(id,project_id,owner_id), FOREIGN KEY(project_id,owner_id) REFERENCES project(id,owner_id)
);
CREATE TABLE memory_revision (
 memory_id uuid NOT NULL REFERENCES memory_item(id), revision integer NOT NULL CHECK(revision>0),
 owner_id uuid NOT NULL REFERENCES principal(id), project_id uuid NOT NULL REFERENCES project(id),
 source_id uuid NOT NULL REFERENCES memory_source(id), content_ref text NOT NULL, content_sha256 char(64) NOT NULL,
 privacy_class text NOT NULL, confidence numeric CHECK(confidence>=0 AND confidence<=1),
 valid_from timestamptz, valid_until timestamptz, conflict_status text NOT NULL DEFAULT 'NONE',
 search_vector tsvector, PRIMARY KEY(memory_id,revision),
 FOREIGN KEY(memory_id,project_id,owner_id) REFERENCES memory_item(id,project_id,owner_id),
 FOREIGN KEY(source_id,project_id,owner_id) REFERENCES memory_source(id,project_id,owner_id)
);
CREATE INDEX ix_memory_search ON memory_revision USING gin(search_vector);
CREATE TABLE context_pack (
 id uuid PRIMARY KEY, owner_id uuid NOT NULL REFERENCES principal(id), project_id uuid NOT NULL REFERENCES project(id),
 task_id uuid REFERENCES task(id), manifest jsonb NOT NULL, sha256 char(64) NOT NULL,
 token_budget integer NOT NULL CHECK(token_budget>0), FOREIGN KEY(project_id,owner_id) REFERENCES project(id,owner_id)
);
CREATE TABLE memory_use_event (
 id uuid PRIMARY KEY, memory_id uuid NOT NULL REFERENCES memory_item(id), task_id uuid REFERENCES task(id),
 attempt_id uuid REFERENCES task_attempt(id), context_pack_id uuid REFERENCES context_pack(id),
 stage text NOT NULL CHECK(stage IN ('retrieved','included','used_by_worker','judged_unused','candidate_helped')),
 observer text NOT NULL, confidence numeric CHECK(confidence>=0 AND confidence<=1),
 occurred_at timestamptz NOT NULL DEFAULT now()
);

-- 0004_telemetry
CREATE TABLE routing_decision (
 id uuid PRIMARY KEY, task_id uuid NOT NULL REFERENCES task(id), attempt_id uuid REFERENCES task_attempt(id),
 candidates jsonb NOT NULL, selected_backend text, policy_decision_id uuid REFERENCES policy_decision(id),
 estimate_status text NOT NULL CHECK(estimate_status IN ('KNOWN','ESTIMATED','UNKNOWN')), created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE routing_outcome (
 id uuid PRIMARY KEY, routing_decision_id uuid NOT NULL REFERENCES routing_decision(id), task_id uuid NOT NULL REFERENCES task(id),
 verifier_refs jsonb NOT NULL, outcome text NOT NULL, observed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE user_correction (
 id uuid PRIMARY KEY, owner_id uuid NOT NULL REFERENCES principal(id), project_id uuid NOT NULL REFERENCES project(id),
 task_id uuid REFERENCES task(id), original_artifact_id uuid REFERENCES artifact(id), correction_artifact_id uuid REFERENCES artifact(id),
 consent_ref jsonb NOT NULL, privacy_class text NOT NULL
);
CREATE TABLE exposure_observation (
 id uuid PRIMARY KEY, task_id uuid NOT NULL REFERENCES task(id), attempt_id uuid REFERENCES task_attempt(id),
 dimension text NOT NULL CHECK(dimension IN ('AUTHORIZED','ACCESSIBLE','OBSERVED')),
 provider text, policy_decision_id uuid REFERENCES policy_decision(id), manifest jsonb NOT NULL, observed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE usage_observation (
 id uuid PRIMARY KEY, task_id uuid NOT NULL REFERENCES task(id), attempt_id uuid REFERENCES task_attempt(id),
 metric text NOT NULL, unit text NOT NULL, amount numeric, confidence text NOT NULL CHECK(confidence IN ('KNOWN','ESTIMATED','UNKNOWN')),
 CHECK((confidence='UNKNOWN' AND amount IS NULL) OR (confidence<>'UNKNOWN' AND amount IS NOT NULL AND amount>=0))
);
CREATE TABLE hardware_manifest (
 id uuid PRIMARY KEY, captured_at timestamptz NOT NULL DEFAULT now(), simulated boolean NOT NULL, body jsonb NOT NULL, sha256 char(64) NOT NULL
);

-- 0005_research
CREATE TABLE research_request (
 id uuid PRIMARY KEY, goal_id uuid NOT NULL REFERENCES goal(id), owner_id uuid NOT NULL REFERENCES principal(id),
 project_id uuid NOT NULL REFERENCES project(id), constraints jsonb NOT NULL, question_ref text NOT NULL,
 FOREIGN KEY(goal_id,project_id,owner_id) REFERENCES goal(id,project_id,owner_id), UNIQUE(id,goal_id)
);
CREATE TABLE source_snapshot (
 id uuid PRIMARY KEY, research_request_id uuid NOT NULL REFERENCES research_request(id), goal_id uuid NOT NULL REFERENCES goal(id),
 requested_url text NOT NULL, canonical_url text NOT NULL, redirect_receipts jsonb NOT NULL,
 fetched_at timestamptz NOT NULL, fetch_status integer NOT NULL, mime_type text NOT NULL,
 raw_artifact_id uuid NOT NULL REFERENCES artifact(id), text_artifact_id uuid REFERENCES artifact(id),
 raw_sha256 char(64) NOT NULL, text_sha256 char(64), extractor_version text NOT NULL,
 completeness text NOT NULL CHECK(completeness IN ('COMPLETE','TRUNCATED','UNSUPPORTED','ERROR')),
 text_size_bytes bigint CHECK(text_size_bytes>=0), UNIQUE(id,research_request_id),
 FOREIGN KEY(research_request_id,goal_id) REFERENCES research_request(id,goal_id)
);
CREATE TABLE claim (
 id uuid PRIMARY KEY, research_request_id uuid NOT NULL REFERENCES research_request(id), claim_artifact_id uuid NOT NULL REFERENCES artifact(id),
 sha256 char(64) NOT NULL, claim_kind text NOT NULL CHECK(claim_kind IN ('FACT','INTERPRETATION','OPINION','QUESTION')),
 support text NOT NULL CHECK(support IN ('PENDING','SUPPORTED','CONTRADICTED','INSUFFICIENT','UNKNOWN')), UNIQUE(id,research_request_id)
);
CREATE TABLE claim_passage (
 claim_id uuid NOT NULL REFERENCES claim(id), snapshot_id uuid NOT NULL REFERENCES source_snapshot(id),
 research_request_id uuid NOT NULL REFERENCES research_request(id), start_offset bigint NOT NULL CHECK(start_offset>=0),
 end_offset bigint NOT NULL, offset_unit text NOT NULL CHECK(offset_unit='utf8-byte'),
 text_sha256 char(64) NOT NULL, normalization_version text NOT NULL,
 quote_verdict text NOT NULL CHECK(quote_verdict IN ('PASS','FAIL','UNKNOWN','NOT_APPLICABLE')),
 PRIMARY KEY(claim_id,snapshot_id,start_offset,end_offset), CHECK(end_offset>start_offset),
 FOREIGN KEY(claim_id,research_request_id) REFERENCES claim(id,research_request_id),
 FOREIGN KEY(snapshot_id,research_request_id) REFERENCES source_snapshot(id,research_request_id)
);
CREATE TABLE verification_report (
 id uuid PRIMARY KEY, research_request_id uuid NOT NULL REFERENCES research_request(id), report_artifact_id uuid NOT NULL REFERENCES artifact(id),
 model_ref text, rubric_ref text, corpus_ref text, verifier_version text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);

-- 0006_plans_fleet
CREATE TABLE plan_version (
 id uuid PRIMARY KEY, goal_id uuid NOT NULL REFERENCES goal(id), contract_id uuid NOT NULL REFERENCES goal_contract(id),
 version integer NOT NULL CHECK(version>0), parent_plan_id uuid REFERENCES plan_version(id), body jsonb NOT NULL,
 sha256 char(64) NOT NULL, UNIQUE(goal_id,version), UNIQUE(id,goal_id),
 FOREIGN KEY(contract_id,goal_id) REFERENCES goal_contract(id,goal_id)
);
CREATE TABLE plan_task_link (
 plan_id uuid NOT NULL REFERENCES plan_version(id), task_id uuid NOT NULL REFERENCES task(id), goal_id uuid NOT NULL REFERENCES goal(id),
 PRIMARY KEY(plan_id,task_id), FOREIGN KEY(plan_id,goal_id) REFERENCES plan_version(id,goal_id),
 FOREIGN KEY(task_id,goal_id) REFERENCES task(id,goal_id)
);
CREATE TABLE workspace_manifest (
 id uuid PRIMARY KEY, attempt_id uuid NOT NULL UNIQUE REFERENCES task_attempt(id), base_commit text NOT NULL,
 protected_root_ref text NOT NULL, body jsonb NOT NULL, sha256 char(64) NOT NULL
);
CREATE TABLE build_candidate (
 id uuid PRIMARY KEY, goal_id uuid NOT NULL REFERENCES goal(id), contract_id uuid NOT NULL REFERENCES goal_contract(id),
 base_commit text NOT NULL, candidate_commit text NOT NULL, tree_sha text NOT NULL, attempt_membership jsonb NOT NULL,
 required_check_hash char(64) NOT NULL, evidence_artifact_id uuid REFERENCES artifact(id),
 FOREIGN KEY(contract_id,goal_id) REFERENCES goal_contract(id,goal_id)
);
CREATE TABLE release_gate (
 id uuid PRIMARY KEY, release text NOT NULL CHECK(release IN ('R0','R1','R2','R3')), candidate_commit text NOT NULL,
 evidence_artifact_id uuid NOT NULL REFERENCES artifact(id), verdict text NOT NULL CHECK(verdict IN ('PASS','INCOMPLETE','FAIL')), manifest_sha256 char(64) NOT NULL
);
CREATE TABLE dogfood_observation (
 id uuid PRIMARY KEY, release_gate_id uuid NOT NULL REFERENCES release_gate(id), observed_at timestamptz NOT NULL,
 candidate_commit text NOT NULL, record_artifact_id uuid NOT NULL REFERENCES artifact(id)
);
CREATE TABLE mvp_review (
 id uuid PRIMARY KEY, release_gate_id uuid NOT NULL REFERENCES release_gate(id), owner_id uuid NOT NULL REFERENCES principal(id),
 decision text NOT NULL CHECK(decision IN ('ACCEPT','REJECT')), decided_at timestamptz NOT NULL,
 trial_manifest_artifact_id uuid NOT NULL REFERENCES artifact(id), sota_authorized boolean NOT NULL DEFAULT false
);
