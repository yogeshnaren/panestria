# Canonical Contracts — Goals, Tasks, Attempts, Approvals, Evidence and Events

**Status:** proposed implementation contract; validate schemas via Alembic, Pydantic tests and DBOS adapter tests before binding public API. **Maintainer:** kernel. **Scope:** initial R0 contract plus forward-compatible target schemas (later migrations are *not* required to ship R0).

## 1. Data model and invariants

### Entity inventory

| Entity | Authoritative responsibilities | R0? |
|---|---|---|
| `principal` | Local owner identifier; auth identity, not subscription secret | yes, seeded |
| `project` | Root, owner, independent trust profile + version | lightweight R0, policy later |
| `goal` | Desired outcome, owner, selected contract version, lifecycle | yes |
| `goal_contract` | Immutable serialized version, content hash, acceptance plan | yes |
| `task` | Goal-linked DAG node, current state, priority, attempt counter | yes |
| `task_attempt` | Started worker, lease epoch, status, process ref, bounds | yes |
| `workflow_link` | DBOS workflow ID + task and attempt for recovery | yes |
| `acceptance_check` / `check_run` | Executable check definition and observed outcome | yes |
| `artifact` | Immutable evidence pointer + hash + privacy class | yes |
| `approval_request` | Digest-bound exact pending action, expiry, decision | yes |
| `task_event` | Replayable canonical task/goal events with one globally ordered commit cursor | yes |
| `side_effect` | External action idempotency, attempt, outcome/reconciliation | mock R0, harden R1 |
| `policy_decision` | Which rule granted/denied access with policy version | skeleton R0, R1 enforcement |
| `memory_item`, `memory_use_event` | Owner/project memory plus 5-stage attribution | schema R1 |
| `routing_decision/outcome` | Provider eligibility/selection and observed quality/cost | R1 evidence capture |
| `research_source`, `claim_evidence` | Fetched page snapshots, quote offsets, supported claims | R2 |
| `entitlement`, `usage_observation` | Provider plan/API authorized path, quota signal confidence | R4 |

### Identifiers and invariants
- Use UUIDv7 if an already-approved library is pinned and tested; UUIDv4 is an acceptable R0 simplification. Never derive identity from a user-provided pathname.
- Timestamps UTC with timezone; task and contract `schema_version` explicit. IDs never recycled; no mutable contract payload after approval.
- Source of truth is one PostgreSQL database. AgentOS domain tables and DBOS-managed tables use separate schemas; a DBOS datasource transaction writes task state, its event and the durable transaction result with the same session and commit. Do not take a DBOS replay result as an authorization decision.
- `goal_contract` rows are append-only; a revision creates a new row with `(goal_id, version)` unique.
- `task_attempt` always belongs to a task; `(task_id, attempt_number)` and `(task_id, lease_epoch)` unique. A newer epoch fences an older worker from committing results.
- `task_event` append in the same transaction as its associated state change, with one global `seq BIGINT GENERATED ALWAYS AS IDENTITY` cursor for task and goal events; ordered append holds the shared transaction lock through commit. SSE may duplicate events but may not invent or skip them.
- `approval_request` binds `effect_digest`, `policy_version`, `owner`, `project`, expiry and minimum actor identity; change to any of these invalidates it.
- `artifact.sha256` verifies bytes of stored artifact; content files reside outside a worker-writable root or are atomically copied to a protected store.
- Every persistence write checks owner/project scope. R0 has one seeded owner but schema is not built around implicit global tenancy.

## 2. Proposed v1 PostgreSQL migration blueprint

These are *illustrative domain tables* for writing the first real migration, not a claim of validated SQL. Use Alembic and test with the pinned PostgreSQL version, DBOS schema, and SQLAlchemy models. Prefer enum/check constraints consistent with code; no app writes to DBOS internal tables.

```sql
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
```

**Event ordering decision (locked for R0):** `task_event` is the only domain event table. One database-generated global `seq` covers both task and goal events (`task_id` nullable). UUID `id` remains stable event identity. Replay uses `WHERE goal_id=:scoped_goal AND seq>:after ORDER BY seq LIMIT :page_size`; SSE ID is `seq`, never timestamp or a per-task counter. Filtering owner/project is mandatory. Clients advance only to the last returned event, handle duplicates and tolerate gaps. Expired retention cursors receive a resync-required response plus an authoritative scoped snapshot.

PostgreSQL sequence allocation alone is not commit ordering: a later value could otherwise be delivered before an earlier transaction commits. All domain-event writers must acquire `pg_advisory_xact_lock(106971,1)` **before allocating any event sequence**, after domain row locks, and retain it until commit/rollback. Insert events as the final application write; no network calls or additional domain-lock acquisition while holding it. Set the backing sequence CACHE to 1, disallow caller-supplied seq and runtime sequence reset, restrict inserts to the ordered append path, bound lock wait and transaction duration. PostgreSQL/DBOS internals retain their own managed locks; test compatibility and deadlock retries on the pinned release. The serialized event append is a deliberate low-volume personal-runtime trade-off, not a distributed-throughput claim. Test concurrent sessions where the first writer pauses before commit: the next event writer must wait, and reconnect must never miss a late lower sequence. Rollbacks may consume numbers; contiguity is not required.

**Atomic state/event decision:** each durable transition uses one DBOS datasource transaction, same PostgreSQL database/session for guarded `task.state` / `row_version` update, `task_event` insert and DBOS-managed transaction result. Do not manually commit inside the callback or write DBOS internal tables. Creating the datasource before launch and pinning its migration/API are AOS-003 plan checks. API admission writes outside a workflow are ordinary transactions and still need request deduplication. There is no second application state store or compensating reconciliation for a half-committed state/event pair. Worker processes, artifact bytes and Git/remote effects remain outside the database transaction.

**Approval scope decision:** `effect_digest` is the only approval fingerprint field. Compute it over canonical exact action payload, owner, project, candidate/base hashes, check set, policy version, minimum actor and expiry. `project_id` is mandatory, including a seeded synthetic project in R0; composite foreign keys reject an approval whose goal/task or owner/project disagree. Authenticating/authorizing the actor, validating policy freshness, one-time consumption and checking the payload against the digest remain service guards and must be tested, not inferred from the existence of a row.

## 3. Structured goal contract and canonical acceptance types

The seven allowed discriminators, field shapes, staged availability and skill migration are defined in [acceptance checks](04-ACCEPTANCE-CHECKS-AND-SKILL-MIGRATION.md), [type registry](../contracts/acceptance-check-types.json) and [node schema](../contracts/acceptance-check.schema.json). There are no spelling aliases in active v1 admission; any legacy conversion is explicit and reviewed.

```yaml
schema_version: 1
goal_id: <generated-uuid>
contract_version: 1
owner_id: <local-principal-uuid>
project_id: <approved-project-uuid>
intent: "Improve maintainability of the synthetic repository"
privacy_class: RESTRICTED
trust_profile_id: SYNTHETIC_DEV
autonomy_profile_ref: default-v1
constraints:
  allowed_paths: ["src/**", "tests/**"]
  forbidden_paths: [".env*", ".git/config", "secrets/**"]
  permitted_capabilities: ["scoped-file-edit", "trusted-test-runner"]
  cloud_egress: deny
budget:
  max_attempts_per_task: 2
  max_wall_seconds: 120
  max_api_usd: 0
acceptance:
  - id: AC-001
    description: "Trusted unit tests pass"
    required: true
    verifier:
      type: trusted-command-ref
      command_ref: synthetic-test-suite # resolved from reviewed registry
      expected_exit_code: 0
      timeout_seconds: 30
    evidence: {required: true, kind: test-report}
  - id: AC-002
    description: "No unauthorized paths modified"
    required: true
    verifier:
      type: git-diff-path-check
      allowed_paths: ["src/**", "tests/**"]
      forbidden_paths: [".env*", ".git/config", "secrets/**"]
    evidence: {required: true, kind: diff-report}
  - id: AC-003
    description: "Merge always requires approval"
    required: true
    verifier:
      type: policy-decision
      action: protected-merge
      expected: approval-required
    evidence: {required: true, kind: policy-report}
non_goals: ["production deployment", "dependency upgrades"]
```

**Validation rules:** no arbitrary `command` string from model/user under `trusted-command-ref`; bounded resource limits; verified `project_root`, owner and policy; referenced checker exists and is signed/trusted; all required check definitions well-typed. `UNKNOWN` must not count as `PASS`.

## 4. Task state transitions and guard contract

Canonical states `CREATED`, `VALIDATING`, `READY`, `LEASED`, `RUNNING`, `WAITING_APPROVAL`, `VERIFYING`, `RETRY_WAIT`, `RECONCILING`, `CANCELLING`, `COMPLETED`, `FAILED`, `CANCELLED`, `REJECTED`.

- `CREATED→VALIDATING`: schema/owner/project/goal contract bound.
- `VALIDATING→READY` only if approved contract and relevant policy checks pass.
- `READY→LEASED` only if capacity, retry budget and lease epoch committed atomically.
- `LEASED→RUNNING`: confirmed worker process handle and valid epoch.
- `RUNNING→VERIFYING`: worker produced immutable candidate artifacts.
- `VERIFYING→COMPLETED`: every required verifier passed and any required effect approval is settled.
- `RUNNING→RECONCILING`: effect may have occurred but result unavailable. No blind retry.
- `WAITING_APPROVAL→READY`: approved exact digest and policy still valid.
- `RUNNING→CANCELLING→CANCELLED` only after effect reconciliation; otherwise hold `RECONCILING`.
- Transition guard writes event and state in one DB transaction; compare expected state/version + lease epoch.
- Terminal states are immutable except explicitly versioned administrative correction events; no worker can resurrect them.

**Error taxonomy:** `POLICY_DENIED`, `CONTRACT_INVALID`, `AUTH_REQUIRED`, `ENTITLEMENT_UNAVAILABLE`, `PROVIDER_THROTTLED`, `WORKER_FAILED`, `WORKER_LOST`, `VERIFY_FAILED`, `AMBIGUOUS_SIDE_EFFECT`, `BUDGET_EXCEEDED`, `CAPACITY_UNAVAILABLE`, `SOURCE_UNTRUSTED`, `DATA_LABEL_UNCERTAIN`, `INTERNAL_ERROR`. Errors carry recoverability, safe-to-retry flag, user-action-needed, and redacted diagnostic ID.

## 5. Worker adapter model and normalized events

```python
class WorkerAdapter(Protocol):
    async def capabilities(self) -> CapabilityManifest: ...
    async def validate(self, spec: JobSpec) -> ValidationResult: ...
    async def start(self, spec: JobSpec) -> ExecutionHandle: ...
    async def events(self, handle: ExecutionHandle) -> AsyncIterator[WorkerEvent]: ...
    async def observe(self, handle: ExecutionHandle) -> RunStatus: ...
    async def cancel(self, handle: ExecutionHandle) -> CancellationReceipt: ...
    async def collect(self, handle: ExecutionHandle) -> RunResult: ...
```

`JobSpec` contains goal, task, attempt, contract hash, lease epoch, workspace manifest, capabilities, trust/privacy/autonomy decision IDs, max cost/tokens/turns/duration, network destinations, backend ref, checkpoint/handoff ref, idempotency keys. Adapter `cancel()` returns `REQUESTED/ACKNOWLEDGED/UNKNOWN`, never conflates SIGTERM with durable task cancellation.

Workers never assign the global cursor: kernel persistence allocates task_event.seq through the ordered append path. Persisted events expose UUID id plus global seq; pre-persistence worker events have no seq.

`WorkerEvent` normalized to `{event_id, goal_id, task_id, attempt_id, lease_epoch, kind, producer, occurred_at, policy_decision_id, privacy_class, trace_id, payload_ref, metadata}`. Unknown usage/cost encoded as `{status:"unknown", amount:null}`.

## 6. Loopback API v1 and browser security

| Endpoint | Method | First release | Guard |
|---|---|---|---|
| `/v1/goals` | POST | R0 | authenticated local owner, typed contract |
| `/v1/goals/{id}` | GET | R0 | owner/project scope |
| `/v1/goals/{id}/events?after={cursor}` | GET | R0, SSE later | scoped event replay |
| `/v1/approvals` | GET | R0 | local session |
| `/v1/approvals/{id}/decision` | POST | R0 | exact digest + CSRF + expiry + owner |
| `/v1/goals/{id}/cancel` | POST | R0 | audited request, not false success |
| `/v1/artifacts/{id}` | GET | R0 | owner/label, canonical filesystem path |
| `/v1/ask` | POST | R1 | offline-only guard + memory scope |
| `/v1/research` | POST | R2 | public-web + egress permission |
| `/v1/runtime/status` | GET | R1 | metadata only |
| `/v1/usage` | GET | R3 | confidence + unknown semantics |

API server binds loopback by default; require per-install strong authorization token or authenticated local session and protect browser mutations with origin/CSRF/Host validation. DNS rebinding prevention must validate Host and trusted-origin semantics independent of binding. Redact bodies and artifacts from low-privilege telemetry. No wildcard CORS.

## 7. Memory and learning telemetry contracts (forward schema)

```yaml
memory_use_event:
  memory_id: uuid
  task_id: uuid
  attempt_id: uuid?
  context_pack_id: uuid?
  stage: retrieved | included | used_by_worker | judged_unused | candidate_helped
  attribution_source: retrieval | agent_tool_event | verifier | user_correction
  confidence: 0.0..1.0
  occurred_at: RFC3339
routing_decision:
  task_id: uuid
  candidates: [{backend: string, allowed: bool, reason: string}]
  selected_backend: string?
  policy_version: string
  estimate_quality: known | estimated | unknown
  resource_snapshot_id: uuid?
  cost_estimate_usd: number?
research_source:
  source_id: uuid
  requested_url: string
  canonical_url: string
  redirect_chain: [string]
  fetched_at: RFC3339
  status: integer
  sha256: hex64
  extraction_version: string
  text_store_ref: string
claim_evidence:
  claim_id: uuid
  source_id: uuid
  start_offset: integer
  end_offset: integer
  quote_match: pass | fail | not_applicable
  support_verdict: supported | contradicted | insufficient | unknown
```

`candidate_helped` is *attribution*, not a causality claim. Full eval of memory lift requires matched tasks/ablation; do not infer from raw usage counts.

## 8. API/contract version policy

- Semantic public APIs under `/v1`; JSON `schema_version` on persisted payloads. Events include producer version.
- Database migrations forward-only with documented down/restore strategy (not blindly reversible when lossy). Backups are encrypted and validated by restore drill before risky migration.
- For adapters, exact CLI/SDK version is part of capability manifest; contract tests must pass against pinned version before deploy.
- Server and UI share generated types or a schema-derived client; avoid manually copied status enums.
- MCP exposure (after R1) wraps the same authorized public API; HTTP vs stdio transport never grants permission by itself.

## Acceptance for this shared contract
1. Alembic migration applies to clean PostgreSQL and survives one `upgrade -> simulated rollback/restore -> upgrade` drill.
2. Conflicting state writes cannot both succeed; stale epoch rejected; duplicate request ID returns existing task or a clear conflict.
3. A valid contract roundtrips unchanged with its hash; an edit creates a new immutable version.
4. Every check has a verifiable type and evidence rule; required UNKNOWN prevents completion.
5. Owner and project boundaries prevent unauthorized reads; logs contain no raw secret fields.
6. API restart + SSE replay preserves event ordering and shows correct authoritative status.

## Source pointers
- Master §5, §9, §10 and §17; `00-DECISIONS-AND-INVARIANTS.md`.
- DBOS workflow docs: https://docs.dbos.dev/python/tutorials/workflow-tutorial
- DBOS replay/determinism: https://docs.dbos.dev/architecture
- DBOS transactions/datasources (verified 2026-10-11): https://docs.dbos.dev/python/tutorials/transaction-tutorial
- PostgreSQL sequence semantics: https://www.postgresql.org/docs/current/functions-sequence.html
