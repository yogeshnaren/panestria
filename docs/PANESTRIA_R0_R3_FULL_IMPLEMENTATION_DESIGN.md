# Panestria R0–R3 — full implementation design and plan

**Status:** design/plan only; application tests NOT_RUN. Use individual slice prompts in Cursor. Original reference pack is included separately.


---

<!-- Source: START_HERE.md -->

# Panestria — extensive R0–R3 implementation design and Cursor plan

**Revision:** 1, 2026-10-11. **Repo:** [yogeshnaren/panestria](https://github.com/yogeshnaren/panestria). **Confirmed baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917, README and MIT LICENSE only. **MVP boundary:** R3. **Runtime implementation/test state:** NOT_STARTED / NOT_RUN.

This package provides 31 item plans, 93 bounded coding handoffs, 124 scenario groups and source-clause traceability through the complete MVP. Global architecture, API/state/transaction/security/migration designs resolve interfaces that a coding agent otherwise might invent. Original architecture/specs/skills are preserved. R4–R7 remain visible in the wider coverage roadmap; none of the coding handoffs automatically proceeds to SOTA.

## Read first

1. [Cursor setup and first prompt](CURSOR_START_HERE.md).
2. [Architecture and typed contracts](design/01-ARCHITECTURE-AND-CONTRACTS.md), [DB/migrations](design/02-DATABASE-AND-MIGRATIONS.md), [security/worker/research boundaries](design/03-SECURITY-WORKERS-AND-RESEARCH.md).
3. [API/CLI/UI flows](design/04-API-AND-USER-FLOWS.md), [decisions/compatibility spikes](design/05-DECISIONS-AND-COMPATIBILITY.md) and [verified sources](design/06-VERIFIED-SOURCES.md).
4. [AOS-001 implementation plan](plans/AOS-001-implementation-plan.md), then its first [coding handoff](cursor/prompts/AOS-001-S1.md).
5. [Test execution/evidence](testing/TEST_EXECUTION.md) and [operations/release runbook](operations/RUNBOOK-AND-RELEASE.md).

## Phase entry points

| Stage | Outcome | Detailed plans | Stop/exit |
|---|---|---|---|
| [R0](phases/R0-BUILD-PLAN.md) | Synthetic durable kernel | 001–005 | G0 observed schema/workflow/evidence/approval/recovery |
| [R1](phases/R1-BUILD-PLAN.md) | Offline Ask and one-worker Build | 006–012,014–018,027a | G1 actual policy/OS/adapter/hardware proof |
| [R2](phases/R2-BUILD-PLAN.md) | Verified public-web Delegate | 013,019–023 | G2 deterministic evidence plus support/uncertainty/live brief |
| [R3](phases/R3-BUILD-PLAN.md) | Two-worker Build and Mission Control | 024–026,027b,028–030 | G3 cumulative checks/six faults, 14-day trial and owner review |

Build completion, technical gate PASS and owner-accepted MVP are distinct. Use [MVP acceptance](MVP_ACCEPTANCE_CHECKLIST.md). Owner acceptance does not imply SOTA permission.

## Machine-readable planning artifacts

- [Slices and prerequisites](implementation-slices.json).
- [Functional/acceptance traceability](requirement-traceability.json): every source clause retained and assigned to scenario groups; actual assertion mappings remain implementation work.
- [Scenario catalog](testing/test-catalog.json) and [cumulative gates](testing/release-gates.json).
- [Schemas](schemas/goal-contract.schema.json), [event schema](schemas/task-event.schema.json), [case result schema](schemas/case-result.schema.json), [acceptance schema](schemas/acceptance-check.schema.json).
- [Fixture examples](fixtures/README.md).
- [Wider MVP→SOTA roadmap](PANESTRIA_PHASED_IMPLEMENTATION_PLAN.md), [coverage preservation](FULL_TARGET_COVERAGE.md), [original repaired specs](specification/README.md).
- [Package/design validation report](VALIDATION_REPORT.json): artifact checks only, never runtime or SQL execution proof.

Do not feed the entire large consolidated manual into one coding request. Use the global decisions and one exact slice/plan/dependency subset, require observed tests, review and repeat. Native credential/tool isolation, installed DBOS/CLI APIs, OS enforcement, actual model performance and judge calibration are explicit spikes with fail-closed outcomes; a mock does not settle them.


---

<!-- Source: CURSOR_START_HERE.md -->

# Using this design with Cursor

## Import and context

Open actual panestria repository in Cursor. Place this complete folder at docs/implementation-r0-r3/ (or adjust the document prefix if adjacent). Preserve specification/ and original hashes; source inclusion does not install skills or grant privileges. No GitHub files were pushed by this task.

Read [START_HERE](START_HERE.md), global design/01 through 05 and [AOS-001](plans/AOS-001-implementation-plan.md). Attach exact selected item/prompt as context; a long file existing on disk is not proof the agent read its decisions.

Optionally copy cursor/rules/panestria-implementation.mdc into .cursor/rules/ in the repository. [Official Cursor rules](https://cursor.com/docs/rules) documents that format. The short rule supplies persistent coding guidance; detailed files must still be read explicitly.

## First prompt

~~~text
Read docs/implementation-r0-r3/START_HERE.md, its design/01 through 05,
plans/AOS-001-implementation-plan.md and cursor/prompts/AOS-001-S1.md.
Inspect current repository/instructions; the recorded main baseline was
4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917. Explain differences.
Implement only AOS-001-S1: one installed src/panestria package, strict settings,
typed health endpoint and meaningful unit fixtures, preserving existing license.
Run implemented checks and report exact changes/results/evidence/limitations.
Do not implement domain workflows or later slices. Stop after this slice.
~~~

## Repeat

1. Select next ready slice from implementation-slices.json; prerequisites need actual code/evidence.
2. Have Cursor inventory files, read the plan/design and identify assertions.
3. Implement one vertical slice with meaningful tests; split if inspected work cannot fit about one developer-day.
4. Run changed/dependency checks; require actual command/report/exit results.
5. Review negative/failure behavior. Fix code or document a scoped mistaken-plan ADR; never disable security checks to turn green.
6. Update assertion→requirement traceability and exact node manifest; leave future/live cases NOT_RUN.
7. At phase promotion run cumulative release-gates.json. Missing/skipped/wrong-version/mock-for-live cannot promote.

Use fresh chats at large item boundaries with exact code/evidence/context. Prompts specify files/test IDs. Native login, paid/provider/live tests and OS provisioning remain actual scoped setup actions; this package contains no API secret provisioning.

## Review prompt

~~~text
Review current slice diff against source requirement IDs, item plan and global
transaction/security/API design. Check concrete negative/failure cases and
scope/epoch/digest guards. List actionable issues with file/line and failing
scenario. Run only implemented scoped synthetic checks. Distinguish PASS,
NOT_RUN, SKIP and UNKNOWN. Do not invent release completion or expand scope.
~~~

## MVP stop

Complete R3 candidate, cumulative tests/six faults, 14-day consented trial and owner MVP acceptance. Use MVP_ACCEPTANCE_CHECKLIST.md. Acceptance does not authorize SOTA; no handoff automatically continues to R4.


---

<!-- Source: design/01-ARCHITECTURE-AND-CONTRACTS.md -->

# Panestria R0–R3 implementation architecture and contracts

**Design revision:** 1, 2026-10-11. **Working namespace:** panestria. **Baseline:** GitHub main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917 (README and MIT LICENSE only; HEAD rechecked for this request). **Status:** implementation design, not tested runtime. The owner requested detailed planning through R3; older instructions preferring only current-phase planning do not restrict this requested deliverable. Reconcile each slice with actual code before implementation. No GitHub writes or provider calls were performed.

## Product and completion contract

R0 proves a synthetic durable goal→worker→verification→approval path. R1 gives offline Ask and one-worker Build. R2 adds bounded evidence-based public-web Delegate. R3 adds the second worker, bounded DAG/concurrency, integrated verification, Mission Control and the complete MVP trial. R3 is the owner-confirmed MVP boundary. SOTA R4–R7 remains in the preserved coverage register; no SOTA implementation is included in these slice prompts.

The kernel owns goal/task/attempt/policy/approval/budget/effect/event records. Models produce proposals and candidate artifacts. Completion requires evidence for the current contract and candidate, plus separate authorization for effects. A UI event, model message or process exit cannot alone complete a task.

## Deployment and package boundaries

One Python 3.12 distribution, one pyproject/uv.lock, src/panestria, FastAPI API, Typer CLI, SQLAlchemy/Alembic, PostgreSQL, DBOS datasource workflows. Start with one API process and one durable executor on one Ubuntu host; each worker/reader/verifier is isolated. Only PostgreSQL is authoritative. The API and executor can initially share a process but the code treats worker launch as a process boundary. Phoenix is local and diagnostic; its outage cannot change a task result. Node/React/Vite enters at R3.

| Sub-package | Owns | Allowed inward dependencies |
|---|---|---|
| contracts | Pydantic payloads, enums, protocol interfaces, JSON schemas | Standard library/Pydantic only; no application sub-package |
| policy | Pure policy intersection, labels and reviewed capability interpretation | contracts |
| kernel | Domain services, scoped repositories, task/approval/effect/budget guards | contracts, policy, telemetry interfaces; verifier interfaces live in contracts |
| execution | DBOS workflows, lifecycle, recovery, admission orchestration | kernel and contracts interfaces |
| brokers | Worker/inference/search implementations and process controls | contracts; uses injected policy/sandbox interfaces |
| verification | Trusted check dispatch, candidate tests/diffs, evidence adjudication | contracts; never API/CLI or vendor harness internals |
| resources | Hardware/model capacity observation and bounded admission | contracts |
| memory | Scoped facts, revision/search/context compilation | contracts; injected scoped repository interface |
| research | Source capture, extraction, citations, support and bounded research orchestration | contracts; injected broker/memory/verifier interfaces |
| sandbox | OS profiles, mount/network enforcement, artifact ingress guards | contracts |
| telemetry | Event transport/redacted spans and measurement | contracts; no dependency on API/UI state |
| api / cli | Authenticated transport and user-facing commands | Domain interfaces via app composition; no direct DBOS-table writes |

Composition in bootstrap.py constructs services and adapters. Import Linter prevents cycles and forbids contracts/domain code importing presentation. Repositories live under kernel/repositories and use supplied transaction sessions; they never call commit. Adapter failures become typed outcomes, not undocumented exceptions leaking vendor payloads.

## Exact planned application structure

```text
src/panestria/
  bootstrap.py, config.py
  contracts/{goal,task,attempt,acceptance,approval,event,worker,policy,budget,inference,research,errors}.py
  kernel/{goals,tasks,approvals,leases,effects,budgets,plans,scheduler}.py
  kernel/repositories/{goals,tasks,attempts,approvals,events,effects,memory,research}.py
  execution/{dbos_runtime,task_workflow,recovery,admission,outbox}.py
  brokers/harness/{base,mock,claude,codex,event_parser,process_runner}.py
  brokers/inference/{base,ollama,api,model_manager}.py
  brokers/search/{base,searxng,configured_api}.py
  sandbox/{profiles,docker_runtime,mounts,network,processes,artifact_ingress}.py
  verification/{registry,runner,diff,artifacts,merge,citations,support}.py
  resources/{probe,catalog,admission,benchmark}.py
  memory/{store,search,context,use_events,lifecycle}.py
  research/{sources,extract,fetch,reader,claims,delegate}.py
  telemetry/{events,redaction,tracing,usage,exposure}.py
  api/{main,auth,sessions,csrf,middleware,errors}.py
  api/routes/{goals,approvals,events,artifacts,ask,research,runtime,usage,audit}.py
  cli/{main,goals,approvals,ask,delegate,hardware,evidence,doctor}.py
apps/mission-control/src/{api,hooks,views,components}/
migrations/versions/{0001_kernel,0002_policy_effects,0003_memory,0004_telemetry,0005_research,0006_plans_fleet}.py
tests/{unit,contract,migration,integration,security,chaos,e2e,live}/
```

Paths name ownership, not a demand to create empty modules in the first slice. Create files only when their slice implements a tested path. The naming addendum maps source-spec src/agentos references to src/panestria; preserved originals are not rewritten.

## Goal and acceptance payloads

Use schema_version=1, UUIDv4, UTC RFC3339 timestamps, strict typed fields and explicit owner/project scope. No model-authored approved_by, policy_granted, action_permit or secret values are accepted. All seven canonical verifiers use acceptance[].verifier.type: trusted-command-ref, git-diff-path-check, policy-decision, artifact-exists, human-review, citation-check, rubric-review. Five R0 runners are available first; R2 runners are rejected until implemented/certified.

Store immutable contract.body and SHA256 of canonical post-validation JSON: UTF-8, sorted keys, compact separators, non-finite numbers forbidden, arrays preserve order, content strings preserved exactly. Monetary input is parsed strictly as Decimal and normalized to a fixed decimal string for hashing; keep computed integer micro-USD amounts for accounting. Reject boolean numeric input, ambiguous units, duplicate check IDs and unexpected fields. Version 1 normalization is fixed and tested across restarts. A change creates a new contract version/hash and invalidates prior effect approvals.

Do not silently translate the legacy skill's command/run fields into trusted commands. Review any legacy migration, register only developer-reviewed argv references and retain the original hash. A registered command means permission to request a bounded isolated check; it does not mean untrusted candidate code can run on the host.

## Scope-safe database and migration ownership

The [DDL blueprint](design/02-DATABASE-AND-MIGRATIONS.md) and design/schema-blueprint.sql guide Alembic; they are not an executed migration. Use one physical PostgreSQL database: app schema panestria, DBOS-managed schema(s) dbos. DBOS manages its own migrations; application Alembic never alters DBOS internals. R0 app relations have explicit principal/project/goal/contract/task/attempt bindings; composite foreign keys prevent attaching a contract/attempt/approval to a different task or project.

Use database constraints for all closed state enums, positive version/attempt counters, nonnegative budgets/sizes and required fingerprints. The service checks semantic action authorization, immutable candidate hashes and capability/contract availability. Foreign keys are not a substitute for per-request ownership. Test application reads, background jobs and artifact downloads with owner/project mismatches. RLS is defense in depth only after a tested per-session identity scheme; do not promise RLS while using a bypass-capable DB role.

## State machine and concurrency

Task states: CREATED, VALIDATING, READY, LEASED, RUNNING, WAITING_APPROVAL, VERIFYING, RETRY_WAIT, RECONCILING, CANCELLING, COMPLETED, FAILED, CANCELLED, REJECTED.

| Transition | Guard / durable evidence |
|---|---|
| CREATED→VALIDATING | Typed request, scoped contract/goal, idempotency check |
| VALIDATING→READY | Approved immutable contract, known available capability and effective policy |
| VALIDATING→WAITING_APPROVAL | Contract execution permission needs explicit owner decision |
| VALIDATING→REJECTED | Invalid contract, denied policy or unsupported runner; safe diagnostic |
| READY→LEASED | Dependencies complete, budget/resources reserved, epoch and attempt allocated |
| LEASED→RUNNING | Started process receipt bound to task/attempt/epoch |
| RUNNING→VERIFYING | Candidate copied/hashed into protected evidence; current epoch |
| VERIFYING→WAITING_APPROVAL | Checks PASS and exact protected action awaits approval |
| WAITING_APPROVAL→READY | Approved contract dispatch; continuation_kind=DISPATCH |
| WAITING_APPROVAL→VERIFYING | Approved candidate action; continuation_kind=MERGE or FINALIZE; never rerun completed worker work |
| VERIFYING→COMPLETED | Current required evidence PASS, authorized effects have confirmed receipts |
| RUNNING/VERIFYING→RECONCILING | Effect may have happened, observation missing; no blind repeat |
| RUNNING/VERIFYING→RETRY_WAIT | Classified safe retry, budgets remain, old epoch fenced |
| RETRY_WAIT→READY | Durable delay expires and current policy/dependencies still valid |
| Active→CANCELLING→CANCELLED | Stop admissions, request termination, settle/reconcile effects; no false cancelled receipt |
| Active→FAILED | Non-retryable failure/budget exhaustion; persisted diagnosis |

Store continuation_kind and resume_phase with approval waits. The WAITING_APPROVAL→VERIFYING edge is an explicit design addendum to the older illustrative transitions, needed to avoid launching a worker again after merge approval. Guard with expected row_version and lease_epoch; UPDATE returning zero rows means conflict/fenced, not success. Terminal task state is immutable; corrections create audited records or a new execution. Goal status is aggregated from all required tasks/effects, not the last event seen by UI.

Lock order: scoped goal/contract as needed → tasks in sorted UUID order → attempts/approval/budget/effect rows → global event append lock. Never acquire new domain locks after event sequence allocation. API conflicts return 409; hidden foreign-scope resources return 404. Use database time for leases/expiry and compare current data in guards.

## Atomic DBOS transactions and enqueue

Domain methods accept UnitOfWork/session. Inside a workflow, transition_task runs in a tracked DBOS datasource transaction: validate current guard, update state/row_version/attempt or effect metadata, append ordered events, let DBOS record the result and commit. No callback manually commits or performs network/process/Git I/O. Committed transaction callbacks are not rerun by normal recovery; uncommitted callbacks may retry, so they contain no external effect.

API admission is outside a workflow: one ordinary SQLAlchemy transaction inserts the request deduplication record, goal/contract/tasks, initial events and enqueues via the supported DBOSClient.enqueue_in_transaction API targeting the same system database. The caller commits; do not wait for workflow result before commit. AOS-003 must pin/test that API. If the chosen pinned release cannot provide atomic enqueue, use the explicitly designed admission outbox with deterministic workflow IDs and a deduplicating dispatcher; record the choice instead of writing two uncoordinated stores.

Workflow identity derives from task ID + immutable contract hash + attempt number. Replay uses persisted outputs and IDs. A new approved attempt gets a new identity/epoch. Domain reads/clock/randomness happen in tracked transactions/steps; the workflow body does only deterministic control flow. DB restore includes app and DBOS schemas from one consistent backup.

## Global event cursor and replay

Canonical domain table is task_event; each row has UUID id and one global seq BIGINT GENERATED ALWAYS AS IDENTITY (CACHE 1). Goal-level rows allow task_id=NULL. Acquire pg_advisory_xact_lock(106971,1) before allocating any seq and hold to transaction completion. Domain-event inserts are the last application writes, with no external I/O or new domain row locks afterward. DBOS may write its managed result in that same transaction.

This deliberate serialized append prevents commit-order holes. Bare sequence allocation does not provide commit ordering. Sequence rollback gaps are allowed; the runtime cannot reset/override seq. Query owner/project-scoped events ORDER BY seq after a decimal cursor, emit SSE id as that seq. JSON represents seq as a decimal string to avoid JavaScript precision loss for BIGINT; UI compares BigInt/string IDs, never Number. Reconnect resumes from the last delivered event, deduplicates UUID/seq and fetches an authoritative snapshot if retention invalidates the cursor.

Publish only after commit; transport fanout is a notification hint. A lost notification is recovered from DB replay. Bound per-client buffers, page size, connection lifetime and response bytes; reauthorize on reconnect and session expiry. Test paused first writer, later writer, rollback, duplicate delivery, restart, goal-level events and cursors greater than 2^53.

## Approval and effect protocol

The only fingerprint field is effect_digest. Hash canonical action payload including action_kind, owner/project/task, contract hash/version, policy version, destination/ref, expected base, candidate commit/tree, required check set, minimum actor and expiry. Authorization has three distinct moments: contract admission, permission to perform a specific effect, and single-use consumption immediately before effect dispatch.

Approvals bind a project and exact payload; the owner sees a preview from those hashed fields. Authentication is server-owned. decide() locks PENDING request and records one APPROVED/DENIED/EXPIRED/REVOKED decision with actor/time/event. Preparing the effect locks the request, checks fresh context and inserts one approval_consumption plus PREPARED effect/outbox intent atomically. A duplicate consumer returns its existing effect; it cannot create another differently scoped effect.

Execute Git/process/network actions outside DB transactions through the trusted actor. Persist receipt in a fresh tracked transaction. Response loss becomes UNKNOWN/RECONCILING; query by stable effect identity before repeat. A Git merge uses git update-ref destination candidate expected_base (CAS) under a protected bare repository, not a race-prone host working-tree merge. Candidate evidence is verified before CAS; if base changed, checks/approval invalidate. Reconciliation reads the destination ref and ancestry/receipt: candidate present→confirmed; unchanged base with verified no-effect→retry if still authorized; different/ambiguous result→owner resolution.

R0 merge is synthetic. Native CLI/model tools never get protected-ref credentials or merge authority. User cancellation fences the attempt and stops new actions immediately, but an already-started effect must be reconciled before terminal cancellation is reported.

## Worker protocol and process lifecycle

WorkerAdapter async methods: capabilities()->CapabilityManifest, validate(JobSpec)->ValidationResult, start(JobSpec)->ExecutionHandle, events(handle)->AsyncIterator[WorkerEvent], observe(handle)->RunStatus, cancel(handle)->CancellationReceipt, collect(handle)->RunResult. JobSpec includes IDs/hash/epoch, bounded workspace and sandbox manifests, allowed capabilities/network destinations, context pack ref, runtime version and limits. Handle contains adapter/run ID, boot/process-group identity, creation receipt and native thread/session only when supported and tested.

Use argv arrays without shell=True; fixed executable paths; scrub inherited env to an explicit allowlist; never serialize secret values. Read stdout/stderr concurrently with byte caps and monotonic wall-clock watchdog independent of incoming output. Handle empty/noisy/truncated JSON, huge lines, invalid UTF-8 and closed pipes. Unknown vendor events remain diagnostics; malformed state-bearing messages fail safe. A vendor 'done' maps to a candidate, not COMPLETED.

A process start is an external effect: write intent before start, record handle/receipt, and on a lost receipt inspect the supervised process identity rather than starting another paid run blindly. PID alone is insufficient after reuse/reboot. Cancellation escalates a bounded graceful request to process-group termination; confirm descendants gone or return UNKNOWN. Native resume is disabled until exact-version tests prove it preserves scope; default recovery uses a new bounded attempt after reconciliation.

## Inference, Ask and memory

InferenceProvider accepts typed prompt/messages, model ref, role, local-only/destination policy, context/token/deadline bounds; returns deltas, normalized terminal result and known/estimated/unknown usage. Ollama is the local first adapter. A separately configured API SDK route satisfies the baseline token-broker capability; use only explicitly approved data/destination/budget, secret handles outside untrusted workers, and versioned consent. It cannot be a fallback for Restricted/offline Ask. API provisioning/live calls are a separate implementation action, not part of this documentation task.

Source-linked memory is R1: FTS first, owner/project/privacy/validity/suppression filters before ranking, deterministic tie-breaks, explicit revisions and conflict sets. Context packs include selected source/skill hashes, input lineage, token budget and untrusted-data wrapping. Keep exact standing rules and user pins. Log retrieved/included/used_by_worker/judged_unused/candidate_helped separately, with observer/confidence; successful task or inclusion is not causal proof of help. Raw prompt retention defaults off; persist only consented content/provenance and summaries. Suppression immediately blocks new retrieval/context; backup/provider erasure limitations are shown. No auto compaction or fine-tuning before SOTA.

## Research and evidence

Delegate uses an explicitly configured search provider; SearXNG is the proposed local frontend, its upstream search still discloses query text. If JSON search is unavailable, return setup-required rather than silently changing providers. Fetch runs only in a trusted broker with URI/IP/redirect policy. Prefer HTTPS and GET for pages, no cookies/ambient proxy, bounded DNS/connection/read/total deadlines, redirect count and decompressed body size; TLS hostname/certificate verification uses the original hostname while the connector uses the approved pinned address. Revalidate every redirect/address change; prevent IPv4/IPv6/encoded/private/metadata destinations below the URL parser too.

The isolated reader has raw source input, read-only files and no shell/private credentials/general actor tools. It extracts text and writes only through a validated output channel. HTML/plain text are the initial R2 formats; PDF/JS-required/truncated content is explicit unsupported/incomplete, not fabricated. Reject source HTML execution and decompression/resource bombs.

Canonical extracted text: decode with recorded charset/error status, HTML entities resolved by extractor, normalize NFC and line endings, retain original raw hash and canonical UTF-8 text hash. Evidence offsets are half-open UTF-8 BYTE offsets into this exact retained text. start_offset/end_offset include offset_unit=utf8-byte; boundaries must be valid UTF-8. Quote comparison is case-sensitive NFC plus defined whitespace collapse; never lower-case or strip substantive punctuation/numbers. Re-extraction with a changed version creates new snapshots/offset mappings.

Every factual claim has retained source IDs/hashes/passages. Deterministic citation/quotation verification yields EVIDENCE_PRESENT or failure; it does not prove support. A separate, versioned support verifier returns SUPPORTED/CONTRADICTED/INSUFFICIENT/UNKNOWN with rationale/evidence; independent model family where feasible, honest local limitations otherwise. Correlated duplicate sources are not votes. Output labels uncertainty and requires owner-visible review; the canonical rubric-review runner requires human sign-off when a contract requires that check. Missing judge or incomplete evidence abstains. No result is a factual truth guarantee.

## R3 planning, scheduling, integrated verification and UI

The planner proposes a bounded typed DAG; validator checks cycles, count/depth, exact contract scope, worker availability, acceptance nodes and aggregate budget before atomically creating a plan version. Direct structured inference first; optional LangGraph is a bounded plan/review/revise adapter only, not another authoritative task ledger. Replanning scope/cost/privacy changes requires a new approved contract; retries and plan revisions are independently bounded.

Scheduler claims ready nodes with SQL row locking/CAS and fencing; reserve CPU/RAM/process/known cash budgets in the same domain transaction. Concurrency defaults to one until R3 gate certifies two; eight competing synthetic jobs must never exceed configured cap. Failed/cancelled dependencies prevent dependent dispatch. Unknown native plan capacity means conservative one-at-a-time/cooldown/refusal according to consent, not unlimited use. R4 adaptive economics is out of scope.

Integrate outputs in a separate temporary candidate from an exact common ancestor; detect overlap/conflict and never overwrite another worker result. Re-run the protected required check set against the final tree. Approved effects bind final candidate/base/check hashes. Tests come from a reviewed immutable acceptance bundle mounted separately; a worker cannot delete/modify the tests that decide success. Candidate/new test code still executes only in a no-secret no-network verifier sandbox.

Mission Control has Ask/Delegate/Build intake, goal/task/fleet views, approvals, immutable artifact/diff/test evidence and usage/exposure/trace screens. Use React/TypeScript/Vite, generated OpenAPI types, native accessible controls and plain CSS before adopting extra UI frameworks. Browser session/CSRF/Host/Origin rules come from the API design. SSE is read-only transport; reducers cannot invent completion. Safe markdown strips active HTML and validates link schemes. Error, UNKNOWN, stale approval, offline and reconnect states are first-class. Run keyboard/contrast/synthetic E2E tests.

## Defaults to encode and validate

Defaults are proposed conservative synthetic/pilot limits, configurable only within certified profile envelopes: 2 attempts/task, 1 replan, 1 concurrent worker before R3/2 after; mock deadline 120s, Build 900s, command 30s, cancellation grace 5s, total capture output 1 MiB, event page 200, search subqueries 3, sources 8, redirects 5, extracted/fetched decompressed body 5 MiB/source, research total deadline 180s. API cash cap defaults to zero; live paid routes remain disabled until a scoped cap/consent is set. Model/context/output bounds depend on measured capability and are validated before dispatch. User can lower limits; raising a sandbox envelope requires conformance tests. Hardware warm-p95 target is measured and locked in an ADR; do not fake ≤3s from simulated presets.

## Version/compatibility policy

Pin exact Python/dependencies/images/CLI binaries/model digests when each integration slice runs; record them in a compatibility manifest. Never write invented latest version numbers in a lockfile. Official docs were checked on 2026-10-11; installed behavior is still a required test. DBOS client/datasource migration/API, native vendor login/tool/config restrictions and supported auth mode are compatibility spikes with fail-closed outcomes. A spike failing pauses only the affected capability, not the kernel or offline Ask.


---

<!-- Source: design/02-DATABASE-AND-MIGRATIONS.md -->

# Database and migration implementation design

[schema-blueprint.sql](design/schema-blueprint.sql) combines the repaired base tables with scoped constraints and R1–R3 extensions. It is a design blueprint, not an applied or independently syntax-parsed migration: this planning workspace has no PostgreSQL server/parser. Cursor splits it into Alembic revisions and proves them in disposable PostgreSQL before use.

| Revision | Stage | Ownership / objects | Required proof |
|---|---|---|---|
| 0001_kernel | R0 / 002,003,005 | principal/project/goal/immutable contract/task/dependencies/attempt/workflow_link/check/run/artifact/approval/consumption/event/idempotency; synthetic side_effect skeleton, scope FKs and closed states | Clean apply, SQL scope/state/null rejection, immutable body/delete, optimistic race, identity commit order and consistent restore |
| 0002_policy_effects | R1 / 006–010,027a | Harden leases/effects/outbox/budget, policy/trust/action/capability/sandbox/session metadata; retain R0 approval/consumption primitives | Lease/consume/reservation races, response loss and stale-policy denial |
| 0003_memory | R1 / 011,017 | Source/item/revision/use_event/context_pack; FTS, validity/pin/suppression/retention | Scoped recall, supersession, five stages, source/pin and suppression restoration |
| 0004_telemetry | R1/R3 / 012,014,029 | Route/outcome/correction, usage/exposure observations, hardware/runtime metadata | DB-only restart reconstruction, unknown=null, safe trace and exposure separation |
| 0005_research | R2 / 013,019–023 | Request/snapshot/claim/passage/report; immutable raw/text/extractor/byte-offset versions | Wrong scope/hash/offset rejected; incomplete/truncated status preserved |
| 0006_plans_fleet | R3 / 025–030 | Plan/version/task link, workspace/candidate/fleet, gate/trial/review | DAG and candidate membership, final-tree evidence, distinct build/gate/owner acceptance |

DBOS migrations stay DBOS-owned, in the same physical database and separate schema. App schema is panestria. Provision schema/grants with a migration role; runtime gets minimal privileges and no schema mutation. Workers get no DB credentials. SQL blueprint ALTERs assume a new empty schema; when translating existing populated tables use add-nullable→backfill→constraint validation→NOT NULL instead of blind non-null ALTER.

## Transaction responsibilities

create_goal: validate actor/project and idempotency request hash; insert immutable version/task/check rows and consent/admission; if executable enqueue through supported DBOS client in the same caller-owned transaction; append events last; commit once.

transition_task: compare expected row_version/state/lease_epoch, enforce allowed edge/continuation, mutate domain metadata, append events last, let datasource callback result share commit. Zero changed rows is conflict/fenced. Terminal correction is a new audited record, not resurrection.

decide_approval: lock request; authenticate actor, current digest/scope/policy/expiry; one decision with actor/time/event. Preparing the effect separately consumes it atomically into one stable effect/outbox intent. Execution is outside DB; finalize/reconcile in another tracked transaction.

reserve_budget: lock project budget/reservations, compute integer micro-USD settled+reserved, deny overcap. Unknown cost requires conservative bounded policy/approval; not zero. Release/settle once by stable identity. Subscription quota observation is not API cash.

Lock domain rows deterministically before the global event append lock; no domain locks or network work after sequence allocation. Repositories use supplied sessions and never commit independently.

## Service invariants SQL cannot establish alone

Verifier type enum/spec agreement does not prove a command registry ref is reviewed or a runner installed. DAG FKs do not prove acyclicity or same approved plan; validate scoped edges in services. Artifact/check PASS requires current candidate/contract/epoch and finalized hashed bytes, not another run's success. Approval consumption uniqueness does not prove semantic payload/digest/actor/policy freshness. Native effect receipts, OS guards and UTF-8 passage boundaries require actual adapter/verifier tests.

Application reads and background writes all enforce owner/project. Composite FKs cover contract/task/attempt/artifact and research request/source/claim association; remaining semantic scope checks are explicit security fixtures. RLS is optional defense in depth only after a tested identity/session/role model, not an asserted guarantee.

## Immutable data, backup and retention

Contract rows change by new version; approval metadata is once-only. Source snapshots/extraction changes create new versions, enforced by service/repository guards and restricted writes (add immutable triggers if chosen; test them). Evidence blobs are protected and hash-checked on read. Ordinary runtime cannot reset global seq or bypass ordered append.

Backup app and DBOS schemas consistently plus artifact/version manifest before upgrades. Test isolated restore with vendor/remote launches disabled until unfinished effects/identity/policy are reviewed. Recovery cannot blindly repeat UNKNOWN remote effects. Destructive downgrade needs proof; otherwise restore/forward repair. Event retention returns scoped resync snapshot and cursor floor. Suppressed memory remains excluded from new contexts; physical backup/provider erasure timing stays explicit.


---

<!-- Source: design/03-SECURITY-WORKERS-AND-RESEARCH.md -->

# Security implementation and live integration boundaries

## Explicit threat and principal boundaries

Host API/kernel/DB are trusted application components under the local owner; model-generated repositories, source pages, skills, provider streams and UI-rendered content are untrusted data. Native vendor authentication is a separate secret-bearing principal. Workers cannot access PostgreSQL credentials, owner home, SSH keys, protected artifact store or protected Git refs. Verifiers cannot access provider auth or network. The HTTP broker is the only public-fetch path. The UI cannot grant its own permissions.

Primary Linux backend proposed for R1: hardened Docker process containers, with a dedicated trusted supervisor owning runtime control. Runtime containers are non-root, no privileged flag, read-only root, drop capabilities, no-new-privileges, explicit tmpfs/output/workspace mounts, PID/memory/CPU/wall/output caps, seccomp default plus tested restrictions. No Docker socket is mounted into any worker. Docker availability/permissions are diagnosed; unsupported environments fail certification, never fall back to host shell. Actual image/UID/OS/network rules are pinned/probed in AOS-008. A separate bwrap/VM backend is not required for this MVP.

| Profile | Read/write | Egress | Secret access |
|---|---|---|---|
| mock-no-network | Synthetic candidate; immutable check bundle read-only | None | None |
| restricted-offline | Scoped data through broker, bounded scratch | None; local inference reached through approved supervisor channel, not arbitrary localhost | None |
| verifier | Candidate read-only + trusted checks read-only, scratch/report output | None | None |
| read-only-research | One raw source read-only; bounded scratch/output channel | Reader none; fetch capability mediated by trusted broker | None |
| scoped-code-edit | Exact sanitized attempt root writable; context read-only | Native inference destinations only, with OS-enforced destination policy | Native harness must prove credential isolation from its tool execution |

A worktree and CLI flags are not OS isolation. Resource limits/network allowlists must be measured from inside the effective process. Route model-provider HTTPS through a trusted egress gateway with allowed hosts/ports and anti-private-IP DNS rules; default direct egress denied. If a native CLI bypasses the gateway or tool restrictions, live capability is not certified. Implement the gateway's enforcement as tested infrastructure, not a prompt or the descriptive egress-preflight script.

## Native CLI authentication is a required compatibility spike

Do not mount a credential volume broadly into an untrusted shell just because the CLI needs login. A single UID that reads a token can generally expose it to code running as that UID. The first live edit profile uses confined native file tools and no arbitrary shell, while a separate no-secret verifier executes reviewed checks. Any required bounded shell tool must cross a tested isolated runner/tool gateway that excludes the credential location/environment. If the installed harness cannot implement that separation, remain in the edit-only profile and record the unmet shell tier; do not mark the full AOS-010 profile certified or widen host access.

This plan deliberately isolates the shell-tier spike instead of pretending a generic credential bind mount is safe. The active-spec requirement for bounded Bash is retained as a separately tested capability. An edit-only pilot can be demonstrated, but G1/R3 acceptance for an enabled shell capability requires that gateway/OS proof. A kernel verifier's safe test invocation does not automatically certify the native shell tool.

**Primary bounded-shell integration candidate:** a kernel-owned MCP tool server bound to one attempt presents only run_registered_check(command_ref, candidate_ref) and returns bounded immutable report references. The server fixes actor/project/attempt context from its instance, ignores client claims of approval, validates the command registry and invokes a separate verifier/command container with no vendor credentials. Arbitrary native shell/code tools are disabled. The CLI receives only an explicit trusted MCP config/endpoint; no repo-controlled server definitions. A Claude safe-mode profile disables MCP and therefore remains edit-only; the shell-capable profile must instead use a tested restricted/explicit-settings/strict-MCP combination with ambient customizations rejected. The installed CLI must prove this config/auth behavior before promotion. Codex must likewise prove native tools cannot bypass the gateway; otherwise that profile is unavailable. No gateway signature or compatibility is presumed from this design.

The MCP server is an internal bounded command bridge for MVP Build, not the post-MVP general external-agent front end. Its executable/image/config hashes are part of the capability manifest. Broker requests are scoped to the current attempt and permit only declared commands/deadlines; invalid or stale refs deny before process launch. Its check results still do not authorize merge or contract changes.

For Claude, inspect exact binary/version/auth status and dedicated config provenance. Current docs describe safe-mode disabling customizations while managed policy hooks can remain, restricted mode with explicit tools and no ambient user/project settings, and permission-prompts none denying unanswered prompts. These are complementary controls, not the sandbox. Probe combined mode/auth behavior; reject unexpected managed hooks/settings. Inject trusted context via the supported prompt-file channel when workspace instructions are disabled. Bare/API mode is not assumed subscription-compatible. No permission bypass flags.

For Codex, use its supported exec/JSONL interface and login status probe, pinned profiles and workspace. Protect local config/auth state from repo content; apply native and outer OS confinement, especially read scopes. Default resume disabled until tested. Current official docs establish the interface; malformed events, version drift, auth/billing mode and actual file/network restrictions still need fixture/live checks. Headless approval suppression is not permission to bypass kernel/OS policy.

## Three-axis policy

Privacy order PUBLIC < INTERNAL < CONFIDENTIAL < RESTRICTED; unknown label denies pending owner resolution. Derived data inherits maximum sensitivity unless a separately reviewed downgrade exists. Trust certification controls tested runtime/capability envelope per project. Autonomy controls which actions need approval. Capability/OS/provider constraints intersect all three; any denial wins. A model can propose a request, never supply proof that it is authorized.

PolicyRequest contains owner/project/task/attempt, action, capability, data refs/labels, destination, trust/privacy/autonomy versions, budget, current time and intended effect. Permit contains policy_decision_id, scope, expiry and enforcement requirements; ApprovalNeeded is not Permit. Revalidate before every future effect; replaying an old DBOS result cannot renew authorization. Test every axis alone and all sensitive path/destination/action pairs.

## Local API/browser identity

Loopback API starts with one seeded owner and a cryptographically random scoped CLI token stored in a local 0600 file. CLI uses Authorization header; tokens never appear in URLs. Browser obtains a short-lived session through a one-use locally displayed pairing code entered on the loopback page; rate-limit/expire codes and bind pairing to exact permitted Host/Origin. Browser mutations require a per-session CSRF token plus HttpOnly SameSite=Strict session cookie and exact origin. Cookie Secure when HTTPS is enabled; do not claim TLS protection for loopback HTTP. Remote access is disabled in MVP.

Validate Host independently of loopback binding. Origin-bearing requests must match the configured first-party origin; missing Origin is allowed only for authenticated non-browser CLI flow, never as a blanket mutation bypass. Content type/body/rate limits are enforced. R3 serves built UI on the same API origin; development Vite origin is an explicitly separate allowlisted profile, never wildcard CORS. SSE supports cookie auth plus origin checks; CLI uses bearer header. Revocation/expiry stops reconnect and privileged actions. Local malicious same-user software is outside the cookie/bearer protection claim; OS principal isolation is still needed.

## Artifact and Git containment

Canonicalize project roots at owner enrollment; no arbitrary raw download path route. Validate realpath/components/symlinks/hardlinks and file counts/sizes, reject devices/FIFOs. Copy outputs through a trusted ingress broker into a content-addressed protected store, atomic write/rename then hash recheck; DB metadata references only finalized blobs. Crash after blob publish before DB reference leaves an orphan, not a passed task; TTL cleanup checks live refs before deleting. Crash before finalization never exposes a partial evidence blob. Store permissions and labels apply to downloads, logs and UI.

Git worktree management uses a dedicated managed mirror/attempt checkout, disabled hooks/credential helpers/config injection, no original remote credential or writable parent refs. Protect .git indirection and core.hooksPath; test git config include/alternates/submodule/LFS behavior. Submodule/network fetch and unknown filters are off unless independently allowlisted. Protected merge occurs only through the kernel CAS actor into the trusted bare destination; worker Git writes cannot commit the protected action. Tests attempting real host files use synthetic sentinel fixtures, not actual personal secrets.

## SSRF and hostile source defense

Policy denies loopback/private/link-local/metadata/multicast/reserved/non-global addresses, encoded IP forms, unapproved ports/schemes and HTTPS downgrade. Resolve all returned IPv4/IPv6 addresses, reject mixed allowed/denied sets and connect only to a checked address with original SNI/Host/cert verification. Validate redirect targets independently; ignore ambient proxy/env credentials and strip authorization on redirect. Cap compressed/decompressed bytes, charset/extractor work and total time. No direct raw urllib/urlopen convenience path that silently follows redirects/re-resolves unchecked.

Unit tests inject resolver/connector/clock and verify exact pin/TLS/redirect behavior without connecting to the real internet. OS-network tests use isolated fixtures and no host metadata services. Hermetic fake transport does not prove OS confinement; both layers have required cases. Reader/synthesizer receive page text as data and have no send/shell/private filesystem capability. Unsupported PDF/JS/oversized/incomplete tables are labelled incomplete. Render briefs with active HTML disabled and safe URL schemes.

## Concrete evidence required before live authority

Effective mount/process/egress manifest, credential sentinel isolation, malicious repo-config/hook/MCP denial, policy decision IDs, native version/auth/tool profile, signal/cancellation receipt, trusted test bundle hashes and source/privacy attribution. Native login is performed explicitly by the owner through sanctioned tools; no token extraction, account pooling or assumed background consent. Public-web and paid SDK live smokes are separate consented actions when implementing. This design task provisions no secrets.


---

<!-- Source: design/04-API-AND-USER-FLOWS.md -->

# API, CLI and UI contract through R3

All /v1 routes require local identity except liveness and tightly bounded session pairing. Pydantic schemas are the generated OpenAPI source; browser/CLI never hand-copy enums. Internal services receive ActorContext(owner_id, project_id, capabilities, correlation_id), not user-supplied authorization flags. Unknown fields rejected. Error shape: code, message, correlation_id, retryable; safe diagnostics never contain credentials or private filesystem roots.

| Route / method | Request/response | Release / behavior |
|---|---|---|
| GET /healthz | liveness/version/profile | R0; no secrets or model dependency |
| GET /readyz | DB/executor/degraded reason | R0; bounded probe, not invented health |
| POST /v1/goals | GoalCreate(contract, Idempotency-Key)→202 GoalView | R0; immutable version and scoped admission |
| GET /v1/goals/{id} | GoalView(tasks/effects/current version) | R0; foreign scope 404 |
| POST /v1/goals/{id}/contracts | ContractRevision(expected_version, body) | R0; creates immutable new version, invalidates old approval |
| POST /v1/goals/{id}/contract-approval | contract hash/version decision | R0; explicit authenticated execution consent, reuses approval service |
| GET /v1/goals/{id}/events?after=seq | event page / text-event-stream | R0 JSON replay; R1 SSE; seq decimal string |
| POST /v1/goals/{id}/cancel | expected_version + reason→202 request receipt | R0; terminal cancellation only after confirmed/reconciled effects |
| GET /v1/approvals | scoped pending/exact preview | R0; pagination and expiry |
| POST /v1/approvals/{id}/decision | effect_digest, expected_version, decision, Idempotency-Key | R0; one locked decision; duplicate same decision idempotent, conflict 409 |
| GET /v1/artifacts/{id} | protected metadata/content | R0; scoped hash check, no raw path parameter; no-store |
| POST /v1/ask | project_id/question/privacy/request_id→stream or AskResult | R1; local-only, explicit terminal event and provenance |
| POST /v1/memory | explicit approved fact/source/revision | R1; owner-only consented content, no model mass-assignment |
| GET /v1/memory/search | scoped query/limit | R1; validity/suppression before relevance |
| POST /v1/memory/{id}/suppress | explicit suppression receipt | R1; new retrieval/context exclusion; later purge status honest |
| GET /v1/runtime/status | model/hardware/profile/capacity/unknown | R1; no credential content |
| POST /v1/research | bounded ResearchRequest→202 goal/research ref | R2; configured provider/consent, no private browsing |
| GET /v1/research/{id}/evidence | claim/source/passages/status/uncertainty | R2; immutable source refs, safe content |
| POST /v1/goals/{id}/plan | bounded proposal or approved plan version | R3; model proposes, kernel validates and scopes |
| GET /v1/tasks and /v1/workers | typed task/fleet snapshots | R3; canonical DB/observed process states |
| GET /v1/usage | known/estimated/unknown values and caps | R3; unknown amount=null, separate cash/plan observations |
| GET /v1/audit | scoped safe action/exposure records | R3; authorized/accessible/observed distinguished |
| POST /v1/session/pair and /logout | one-use local code→session, csrf metadata | R1/R3 browser; rate limit, strict origin, cookie controls |

Add indexes/pagination, cap request/response bytes and reject invalid media type. Explicit request idempotency is scoped by actor/project/operation/key plus request hash; a repeated key with changed body is 409. Return same logical goal/effect after lost response. Response examples under fixtures/ define data shapes; reference IDs are synthetic.

## CLI journeys

R0: panestria goal submit --contract <fixture>; panestria goal status <id>; panestria goal events <id> --after <seq>; panestria contract approve <id> --digest <sha>; panestria artifact show <id>; panestria approve <request-id> --digest <effect-digest>; panestria deny/cancel. Commands resolve local identity from a protected file, never request arbitrary approved booleans. Domain denial/UNKNOWN returns nonzero or a documented pending exit, not false success.

R1: panestria ask --project <id>; memory add/search/suppress; hardware probe/report/benchmark; doctor. R2: panestria delegate --project <id> --question <text> with configured provider/limits; evidence verify. R3: build --contract <path> proposes validated DAG and shows queue/worker/check/approval states. All output includes safe correlation and evidence IDs.

## Four reference flows

**R0 synthetic Build:** submit validated contract→owner contract consent→atomic workflow enqueue→lease mock attempt→isolated edit→immutable evidence→independent checks→exact merge approval→PREPARED effect→synthetic CAS merge→confirmed receipt→task/goal completion. Restart at every boundary; WAITING_APPROVAL remembers whether to dispatch or finalize.

**Ask:** local identity/project/privacy→FTS recall with validity filters→bounded context pack→local model admission→stream with provenance→terminal status→separate consented correction. Network-off prompt cannot change route. If model missing, show degraded status and keep kernel/API usable.

**Delegate:** approved search disclosure→bounded subqueries/results→checked fetch broker→isolated reader snapshots→structured claims→citation/quote check→support/contradiction labels→brief/artifact/evidence. Reader never gains send/shell privileges; all error/truncation conditions survive output formatting.

**R3 two-worker Build:** approved bounded DAG→resource/known-cash reservations→two separate leases/workspaces→candidate outputs→fenced collection→integration/conflict detection→trusted suite on final tree→exact final approval→protected CAS effect→receipt→complete aggregate. Disjoint isolated passes are insufficient if the combined candidate fails.

## UI state and usability

Pages: intake tabs Ask/Delegate/Build, goals/tasks, task detail with evidence timeline, fleet, approval inbox, usage/exposure and trace links. Minimal accessible CSS/components, keyboard focus/contrast and plain statuses before elaborate graphs. A pending approve action is disabled until exact current preview/digest is loaded; UI cannot change payload after decision. On network failure keep pending state and fetch authoritative status. Source markdown strips active HTML; links never execute local files or scripts.

SSE handler uses idempotent normalized event reducer and decimal cursor; reconnect after last delivered event, bounded retry/backoff, snapshot refresh if cursor retention gap or unknown event schema. Session expiration clears sensitive views and stops reconnection. Unknown usage is visibly unavailable, not $0.0. Exposure fields show what was permitted, what the worker could access and what network metadata was actually observed; encrypted payload contents are not guessed.


---

<!-- Source: design/05-DECISIONS-AND-COMPATIBILITY.md -->

# Detailed-plan decisions and compatibility spikes

The repaired specs and historical architecture are preserved. This user-requested detailed design resolves implementation choices and calls out deltas; Cursor must not hide them by editing originals. Record these as ADRs in the implementing repository before their affected slices.

| Decision | Rationale / implementation consequence | Validation |
|---|---|---|
| D01 namespace panestria | One distribution and package/CLI matching repo; original src/agentos examples remain historical | Install/import/CLI/version tests |
| D02 one PostgreSQL DB + DBOS datasource | State/event/tracked result atomic; separate schemas are ownership, not two task stores | Crash before/after commit; datasource/enqueue API probe |
| D03 identity seq with serialized commit | Global task+goal replay; decimal string at JSON/JS boundary | Delayed writer, gap/rollback and >2^53 fixtures |
| D04 approval consumption relation | Decision and effect consumption are distinct; one effect per exact request | Approve/deny/consume races, changed hashes/actor/project |
| D05 continuation state | Explicit WAITING_APPROVAL→VERIFYING for post-worker merge; no repeated worker after approval | Crash at contract vs merge wait |
| D06 Docker backend + separate verifier | Concrete Linux driver; no credential/network in candidate-code checks | Inside-process filesystem/network/cgroup probes; no unconfined fallback |
| D07 native credential/tool separation spike | Native shell/file tooling cannot read harness login state; edit-only pilot does not certify shell tier | Synthetic credential sentinel; live adapter/OS compatibility gate |
| D08 API bearer vs browser session | Explicit local owner identity and anti-CSRF; same-origin built UI | Host/Origin/missing-header/session/CSRF negative matrix |
| D09 scoped FTS, no raw-prompt retention by default | Useful memory with honest provenance and suppression; richer hybrid lifecycle later | Cross-project, stale/suppressed fact and consent fixtures |
| D10 canonical UTF-8 byte offsets, NFC quotes | One reproducible source/quote coordinate convention; legacy lower-case matcher unsuitable | Non-ASCII boundary, quote edits, re-extraction version |
| D11 SearXNG proposed search frontend | One explicit provider, no silent paid/off-device switch; upstream queries still egress | Instance JSON config/rate-policy probe and query ledger |
| D12 direct typed planner first | Bounded DAG without forcing graph infrastructure; LangGraph adapter only for a measured loop | Cycle/scope/budget/replan tests and output-contract parity |
| D13 independent required test bundle | Worker cannot weaken tests or self-approve | Tampered checks/new tests vs protected fixture tests |
| D14 conservative caps and explicit currency | Cash cap zero until consent; task budgets and API reservation cannot be inferred from plan quota | Concurrent reservation and unknown usage denial |
| D16 canonical approval fields | Historical payload_hash/effect_hash source-clause spelling means effect_digest; active JSON/DB/DTO has only effect_digest | Schema/legacy-field rejection and UI exact-preview tests |
| D17 decimal money at public boundary | max_api_usd is a decimal string (up to six fractional places), normalized for hash/accounting; old prose/YAML numeric examples are migration inputs, not canonical JSON | Reject boolean/NaN/raw float ambiguity and preserve integer micro-USD cap |
| D15 HTML/text R2 scope | No arbitrary JS/PDF execution in reader; unsupported/incomplete visible | MIME/truncation/bomb fixtures and brief uncertainty |

Current documentation checks on 2026-10-11 are source evidence only. Pin exact installed versions with a manifest containing component, resolved version/digest, source URL, supported capability, fixtures/live outcome and operator approval. No latest-version strings or GPU throughput estimates are prefilled.

| Spike | Owner / stage | Required observation | Fail-closed result |
|---|---|---|---|
| DBOS datasource + atomic client enqueue | execution / 003 | Same transaction session, tracking/launch/migration APIs and supported isolation retry | Pause durable admission integration; explicit fallback outbox ADR only |
| Native CLI modes/auth/config/tool isolation | brokers/sandbox / 010,024 | Exact binary modes and sanctioned auth, combined flag behavior, no host auth exposure | Disable affected live worker; synthetic/offline paths remain usable |
| OS backend on actual Ubuntu/kernel/VPN | sandbox / 008 | Effective mounts/UID/cgroups/process and pinned egress policy | Capability unavailable, never host fallback |
| Hardware/local model placement | resources / 015,016,018 | Real VRAM/RAM/power plus model license/latency/quality | Explicit CPU/degraded/no-model state; no hidden cloud |
| Search JSON/policy/retention | research / 019 | Configured SearXNG/API access, consent/quotas/source storage | Delegate setup-required/unsupported provider |
| Independent support judging | verification / 022 | Labeled corpus, safe local model or explicitly eligible route | UNKNOWN/abstain; no fabricated support |
| Phoenix/UI footprint and security | telemetry/UI / 028,029 | Local redacted traces, correct browser auth/reconnect, acceptable resource use | Trace export off or UI error; task truth unaffected; unresolved required UI gate blocks G3 |

Remaining account, pricing, CLI and hardware facts must be rechecked when implementation runs. Planning is authorized here; live vendor use, credential provisioning, OS provisioning and public publishing need their actual scoped user actions. No implementation result is claimed by this document.


---

<!-- Source: design/06-VERIFIED-SOURCES.md -->

# Upstream sources checked for this detailed design

Checked 2026-10-11. These references support interface choices; they do not establish installed-runtime conformance. Keep exact version/behavior evidence in implementing compatibility manifests.

- [DBOS datasource transactions](https://docs.dbos.dev/python/tutorials/transaction-tutorial): tracked database outcomes commit with callback writes; the datasource session is the transaction boundary. This supports the atomic state/event design. Outside a workflow a normal transaction still needs request deduplication.
- [DBOS client](https://docs.dbos.dev/python/reference/client): atomic enqueue participates in a caller-owned transaction against the system database; pin/test the chosen client API.
- [PostgreSQL sequences](https://www.postgresql.org/docs/current/functions-sequence.html): allocation is not rollback-safe/contiguous. The global cursor design adds serialized commit ordering rather than assuming sequence values are commit timestamps.
- [Claude CLI](https://code.claude.com/docs/en/cli-reference): customization/tool/permission controls and prompt-file interfaces are version-specific. Managed policy exceptions and combined auth behavior require testing.
- [Codex non-interactive execution](https://learn.chatgpt.com/docs/non-interactive-mode): exec/JSONL is the supported process integration route; saved authentication and structured output do not grant kernel authorization.
- [Codex command reference](https://learn.chatgpt.com/docs/developer-commands?surface=cli): login status and permission/sandbox profiles are documented. Probe their effective read/write/config/network restrictions on the actual binary; never infer arbitrary host secrecy from a mode name.
- [Docker resource constraints](https://docs.docker.com/engine/containers/resource_constraints/): container resource limits must be configured explicitly; this plan requires measured effective caps.
- [SearXNG search API](https://docs.searxng.org/dev/search_api.html): instance configuration controls permitted formats; JSON/setup/rate behavior is a compatibility check, not assumed availability.
- [Cursor rules](https://cursor.com/docs/rules): project rules are .mdc files under .cursor/rules; the supplied rule template is optional persistent coding guidance. It is not an OS or policy guard.
- [uv project layout](https://docs.astral.sh/uv/concepts/projects/layout/): one project metadata/lockfile and installed src package; use frozen dependency checks when implementing.

The source-order workflow for Codex guidance used the OpenAI Docs skill. This package contains no copied full external documentation pages.


---

<!-- Source: phases/R0-BUILD-PLAN.md -->

# R0 detailed sequence and gate

**Status:** NOT_STARTED / NOT_RUN. **Gate:** G0. Detailed planning through R3 is authorized; code/live conformance remain pending.

| Step | Plan | Slices | Dependencies |
|---|---|---|---|
| 1 | [AOS-001](plans/AOS-001-implementation-plan.md) | AOS-001-S1 → S2 → S3 | repo inventory |
| 2 | [AOS-002](plans/AOS-002-implementation-plan.md) | AOS-002-S1 → S2 → S3 | AOS-001 |
| 3 | [AOS-003](plans/AOS-003-implementation-plan.md) | AOS-003-S1 → S2 → S3 | AOS-002 |
| 4 | [AOS-004](plans/AOS-004-implementation-plan.md) | AOS-004-S1 → S2 → S3 | AOS-003 |
| 5 | [AOS-005](plans/AOS-005-implementation-plan.md) | AOS-005-S1 → S2 → S3 | AOS-003, AOS-004 |

Cumulative gate requires **20 scenario groups** across **5 items**. See [release gates](testing/release-gates.json) and [execution](testing/TEST_EXECUTION.md). Every group must cover all its source acceptance parameters. Missing/skipped/mock-for-live/version-mismatched evidence is INCOMPLETE.

## Demonstration / exit

Synthetic goal/contract consent, mock worktree, independent checks, exact synthetic merge approval and durable recovery. Real PostgreSQL migration/concurrency/atomic enqueue/replay and safe cleanup proven; no live accounts.

Record code, dependency/image/model/CLI/hardware versions, corpus/hash, reports, known issues, runbook and rollback. Do not assume current docs or simulated prototypes are installed-runtime proof.


---

<!-- Source: phases/R1-BUILD-PLAN.md -->

# R1 detailed sequence and gate

**Status:** NOT_STARTED / NOT_RUN. **Gate:** G1. Detailed planning through R3 is authorized; code/live conformance remain pending.

| Step | Plan | Slices | Dependencies |
|---|---|---|---|
| 1 | [AOS-006](plans/AOS-006-implementation-plan.md) | AOS-006-S1 → S2 → S3 | AOS-003 |
| 2 | [AOS-007](plans/AOS-007-implementation-plan.md) | AOS-007-S1 → S2 → S3 | AOS-002 |
| 3 | [AOS-008](plans/AOS-008-implementation-plan.md) | AOS-008-S1 → S2 → S3 | AOS-004, AOS-007 |
| 4 | [AOS-009](plans/AOS-009-implementation-plan.md) | AOS-009-S1 → S2 → S3 | AOS-005, AOS-007 |
| 5 | [AOS-010](plans/AOS-010-implementation-plan.md) | AOS-010-S1 → S2 → S3 | AOS-004, AOS-008, AOS-009 |
| 6 | [AOS-027a](plans/AOS-027a-implementation-plan.md) | AOS-027a-S1 → S2 → S3 | AOS-004, AOS-009, AOS-010 |
| 7 | [AOS-011](plans/AOS-011-implementation-plan.md) | AOS-011-S1 → S2 → S3 | AOS-002 |
| 8 | [AOS-012](plans/AOS-012-implementation-plan.md) | AOS-012-S1 → S2 → S3 | AOS-002, AOS-007 |
| 9 | [AOS-014](plans/AOS-014-implementation-plan.md) | AOS-014-S1 → S2 → S3 | AOS-003, AOS-012 |
| 10 | [AOS-015](plans/AOS-015-implementation-plan.md) | AOS-015-S1 → S2 → S3 | AOS-001 |
| 11 | [AOS-016](plans/AOS-016-implementation-plan.md) | AOS-016-S1 → S2 → S3 | AOS-011, AOS-015 |
| 12 | [AOS-017](plans/AOS-017-implementation-plan.md) | AOS-017-S1 → S2 → S3 | AOS-011, AOS-016 |
| 13 | [AOS-018](plans/AOS-018-implementation-plan.md) | AOS-018-S1 → S2 → S3 | AOS-015, AOS-016, AOS-017 |

Cumulative gate requires **72 scenario groups** across **18 items**. See [release gates](testing/release-gates.json) and [execution](testing/TEST_EXECUTION.md). Every group must cover all its source acceptance parameters. Missing/skipped/mock-for-live/version-mismatched evidence is INCOMPLETE.

## Demonstration / exit

Offline Ask/source-linked memory and one independently verified live worker. Three-axis policy, OS/credential/tool isolation, API security, resource caps, baseline opt-in SDK and telemetry proved. Uncertified native shell tier cannot be declared certified by an edit-only pilot.

Record code, dependency/image/model/CLI/hardware versions, corpus/hash, reports, known issues, runbook and rollback. Do not assume current docs or simulated prototypes are installed-runtime proof.


---

<!-- Source: phases/R2-BUILD-PLAN.md -->

# R2 detailed sequence and gate

**Status:** NOT_STARTED / NOT_RUN. **Gate:** G2. Detailed planning through R3 is authorized; code/live conformance remain pending.

| Step | Plan | Slices | Dependencies |
|---|---|---|---|
| 1 | [AOS-013](plans/AOS-013-implementation-plan.md) | AOS-013-S1 → S2 → S3 | AOS-002, AOS-008 |
| 2 | [AOS-019](plans/AOS-019-implementation-plan.md) | AOS-019-S1 → S2 → S3 | AOS-008, AOS-009, AOS-013 |
| 3 | [AOS-020](plans/AOS-020-implementation-plan.md) | AOS-020-S1 → S2 → S3 | AOS-013, AOS-019 |
| 4 | [AOS-021](plans/AOS-021-implementation-plan.md) | AOS-021-S1 → S2 → S3 | AOS-020 |
| 5 | [AOS-022](plans/AOS-022-implementation-plan.md) | AOS-022-S1 → S2 → S3 | AOS-021, AOS-016 |
| 6 | [AOS-023](plans/AOS-023-implementation-plan.md) | AOS-023-S1 → S2 → S3 | AOS-019, AOS-020, AOS-021, AOS-022 |

Cumulative gate requires **96 scenario groups** across **24 items**. See [release gates](testing/release-gates.json) and [execution](testing/TEST_EXECUTION.md). Every group must cover all its source acceptance parameters. Missing/skipped/mock-for-live/version-mismatched evidence is INCOMPLETE.

## Demonstration / exit

Configured public-web search, pinned safe fetch, isolated reader, exact retained hashes/byte passages/quotes and separate support/uncertainty. Five adversarial briefs and scoped live brief; disabling research leaves Ask/Build working.

Record code, dependency/image/model/CLI/hardware versions, corpus/hash, reports, known issues, runbook and rollback. Do not assume current docs or simulated prototypes are installed-runtime proof.


---

<!-- Source: phases/R3-BUILD-PLAN.md -->

# R3 detailed sequence and gate

**Status:** NOT_STARTED / NOT_RUN. **Gate:** G3. Detailed planning through R3 is authorized; code/live conformance remain pending.

| Step | Plan | Slices | Dependencies |
|---|---|---|---|
| 1 | [AOS-024](plans/AOS-024-implementation-plan.md) | AOS-024-S1 → S2 → S3 | AOS-004, AOS-008, AOS-010 |
| 2 | [AOS-025](plans/AOS-025-implementation-plan.md) | AOS-025-S1 → S2 → S3 | AOS-003, AOS-016 |
| 3 | [AOS-026](plans/AOS-026-implementation-plan.md) | AOS-026-S1 → S2 → S3 | AOS-006, AOS-010, AOS-024, AOS-025 |
| 4 | [AOS-027b](plans/AOS-027b-implementation-plan.md) | AOS-027b-S1 → S2 → S3 | AOS-027a, AOS-026 |
| 5 | [AOS-028](plans/AOS-028-implementation-plan.md) | AOS-028-S1 → S2 → S3 | AOS-005, AOS-014, AOS-017, AOS-023, AOS-027b |
| 6 | [AOS-029](plans/AOS-029-implementation-plan.md) | AOS-029-S1 → S2 → S3 | AOS-012, AOS-014, AOS-028 |
| 7 | [AOS-030](plans/AOS-030-implementation-plan.md) | AOS-030-S1 → S2 → S3 | AOS-017, AOS-018, AOS-019, AOS-020, AOS-021, AOS-022, AOS-023, AOS-024, AOS-025, AOS-026, AOS-027b, AOS-028, AOS-029 |

Cumulative gate requires **124 scenario groups** across **31 items**. See [release gates](testing/release-gates.json) and [execution](testing/TEST_EXECUTION.md). Every group must cover all its source acceptance parameters. Missing/skipped/mock-for-live/version-mismatched evidence is INCOMPLETE.

## Demonstration / exit

Two certified workers, bounded DAG/cash/resource admission, integrated required suite and exact final approval. Mission Control reflects canonical task/evidence/usage/exposure with redacted local traces. A-1/D-1/B-1 and six faults pass, followed by 14-day owner trial/acceptance.

Record code, dependency/image/model/CLI/hardware versions, corpus/hash, reports, known issues, runbook and rollback. Do not assume current docs or simulated prototypes are installed-runtime proof.

Freeze the candidate for [MVP review](MVP_ACCEPTANCE_CHECKLIST.md). Technical build completion precedes observed trial and owner MVP_ACCEPTED. A separate owner record authorizes R4/SOTA; these coding prompts stop at R3.


---

<!-- Source: plans/AOS-001-implementation-plan.md -->

# AOS-001 — Repository scaffold, developer toolchain, CI and local services: implementation plan

**Release:** R0. **Format:** checklist; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** none. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](testing/TEST_EXECUTION.md) and [source spec](specification/specs/AOS-001.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

An unassisted developer can clone, bootstrap and test a modular-monolith project on supported Ubuntu without a cloud account or real model subscription.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/config.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/api/main.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/api/health.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/cli/main.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `create_app(settings, readiness_probe) -> FastAPI`
- `Settings.validate_profile() -> ValidatedSettings`
- `HealthService.readiness(deadline) -> Readiness`

**Migration ownership:** Alembic scaffold only; no domain tables.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-001-F01 | Use one Python 3.12+ distribution managed by `uv`, one `pyproject.toml`/lockfile and `src/agentos/` with `contracts`, `kernel`, `execution`, `brokers`, `policy`, `resources`, `memory`, `telemetry`, `verification`, `api` and `cli` sub-packages; reserve `apps/mission-control` for React/Vite later but do not require Node to execute the R0 API tests. | AOS-001-S1, AOS-001-S2, AOS-001-S3; owning files/interfaces above | AOS-001-TC01, AOS-001-TC02, AOS-001-TC03, AOS-001-TC04; parameterize every condition in this clause |
| AOS-001-F02 | Pin Python/Node dependencies, create `pyproject.toml`, lint/type/test commands, Alembic location, `.env.example` containing *only placeholders*, Docker Compose PostgreSQL with health check and persistent named volume. | AOS-001-S1, AOS-001-S2, AOS-001-S3; owning files/interfaces above | AOS-001-TC01, AOS-001-TC02, AOS-001-TC03, AOS-001-TC04; parameterize every condition in this clause |
| AOS-001-F03 | Document environment variable names, process modes, deterministic seeded synthetic project, local-only service binding, `make`/`just` commands and an offline dependency-cache strategy. No runtime arbitrary `pip install`. | AOS-001-S1, AOS-001-S2, AOS-001-S3; owning files/interfaces above | AOS-001-TC01, AOS-001-TC02, AOS-001-TC03, AOS-001-TC04; parameterize every condition in this clause |
| AOS-001-F04 | CI runs Ruff, Mypy, Import Linter boundary checks, unit and migration smoke tests; integration tests start an ephemeral DB and detect schema drift. Protect repo scripts from unreviewed auto-execution. | AOS-001-S1, AOS-001-S2, AOS-001-S3; owning files/interfaces above | AOS-001-TC01, AOS-001-TC02, AOS-001-TC03, AOS-001-TC04; parameterize every condition in this clause |
| AOS-001-AC01 | Fresh Ubuntu VM bootstraps from clean checkout using documented commands. | AOS-001-S1, AOS-001-S2, AOS-001-S3; owning files/interfaces above | AOS-001-TC01, AOS-001-TC02, AOS-001-TC03, AOS-001-TC04; parameterize every condition in this clause |
| AOS-001-AC02 | CI enforces Ruff, MyPy, Pytest, dependency-lock reproducibility and basic secret scanner; unit tests run without provider credentials. | AOS-001-S1, AOS-001-S2, AOS-001-S3; owning files/interfaces above | AOS-001-TC01, AOS-001-TC02, AOS-001-TC03, AOS-001-TC04; parameterize every condition in this clause |
| AOS-001-AC03 | PostgreSQL service is healthy and migration check returns zero; API inaccessible from non-loopback interface; no unexpected egress during smoke test. | AOS-001-S1, AOS-001-S2, AOS-001-S3; owning files/interfaces above | AOS-001-TC01, AOS-001-TC02, AOS-001-TC03, AOS-001-TC04; parameterize every condition in this clause |
| AOS-001-AC04 | Failing lint/test/prohibited dependency injection makes CI fail; no real keys in commit, build image or logs. | AOS-001-S1, AOS-001-S2, AOS-001-S3; owning files/interfaces above | AOS-001-TC01, AOS-001-TC02, AOS-001-TC03, AOS-001-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-001-S1](cursor/prompts/AOS-001-S1.md) | repository inventory | One installed src/panestria package, strict settings and typed health with unit fixtures; preserve MIT/license and write naming ADR. | AOS-001-TC01; command/report/exit, immutable evidence and diff |
| [AOS-001-S2](cursor/prompts/AOS-001-S2.md) | AOS-001-S1 | Frozen dependency/bootstrap commands, Ruff/Mypy/Import Linter, provider-free CI and deliberately failing boundary fixtures. | AOS-001-TC02; command/report/exit, immutable evidence and diff |
| [AOS-001-S3](cursor/prompts/AOS-001-S3.md) | AOS-001-S2 | Scoped PostgreSQL Compose/migration scaffold, fresh-machine/offline-cache/loopback/reset proof and setup runbook. | AOS-001-TC01, AOS-001-TC02, AOS-001-TC03, AOS-001-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-001-TC01 | unit | `tests/integration/test_aos_001.py::test_config_and_health` | Valid SYNTHETIC_DEV config and unavailable DB produce truthful bounded health; invalid bind/secret-bearing output rejected. |
| AOS-001-TC02 | contract | `tests/integration/test_aos_001.py::test_import_and_lock_failures` | A disposable forbidden import, stale lock, failing lint/type/unit each fail its gate; positive installed src imports pass. |
| AOS-001-TC03 | integration | `tests/integration/test_aos_001.py::test_database_bootstrap_cleanup` | Fresh scoped DB is healthy, empty Alembic scaffold applies, wrong-volume/symlink cleanup denied. |
| AOS-001-TC04 | live | `tests/integration/test_aos_001.py::test_fresh_host_loopback` | Fresh supported Ubuntu bootstrap, dependency cache and no-egress runtime smoke require no AI credentials; record real sockets/startup/RSS. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_001.py --junitxml=evidence/AOS-001.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.


---

<!-- Source: plans/AOS-002-implementation-plan.md -->

# AOS-002 — Goal contracts, tasks, attempts and database migration v1: implementation plan

**Release:** R0. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-001. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](testing/TEST_EXECUTION.md) and [source spec](specification/specs/AOS-002.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

A goal is represented by an immutable, structured, validated contract, with a persisted task DAG and attempt history supporting optimistic concurrency and executable acceptance criteria.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/contracts/goal.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/contracts/acceptance.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/contracts/task.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/goals.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/tasks.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/repositories/goals.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/repositories/tasks.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `GoalService.submit(actor, request, idempotency_key) -> GoalReceipt`
- `ContractService.revise(actor, goal_id, expected_version, body) -> ContractVersion`
- `TaskService.transition(uow, task_id, expected_version, epoch, target, cause) -> TransitionReceipt`
- `PlanValidator.validate_dag(nodes, edges, contract) -> ValidatedPlan`

**Migration ownership:** 0001_kernel: principal/project/goal/contract/task/dependency/attempt/workflow_link/check/artifact/approval/event/idempotency; scope FKs, immutable contracts and ordered seq.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-002-F01 | Implement Pydantic v2 models for principal/project/goal/GoalContractVersion/task/task dependency/attempt/check and artifact/approval IDs, normalizing UTC timestamps and rejecting unknown unsafe fields. | AOS-002-S1, AOS-002-S2, AOS-002-S3; owning files/interfaces above | AOS-002-TC01, AOS-002-TC02, AOS-002-TC03, AOS-002-TC04; parameterize every condition in this clause |
| AOS-002-F02 | Create Alembic migration for R0 entities in `01-CANONICAL-DATA-AND-API-CONTRACTS.md` with typed constraints, indexes, foreign keys, unique `(goal_id, version)` and guarded state transitions. Use one transaction to write state plus canonical event. | AOS-002-S1, AOS-002-S2, AOS-002-S3; owning files/interfaces above | AOS-002-TC01, AOS-002-TC02, AOS-002-TC03, AOS-002-TC04; parameterize every condition in this clause |
| AOS-002-F03 | Convert narrative acceptance lines into typed verifier nodes from the seven-value canonical registry and discriminated schema in `contracts/`; R0 implements the five R0 types, while R2 runners fail admission until installed and approved; never accept worker-supplied shell as a trusted verifier. | AOS-002-S1, AOS-002-S2, AOS-002-S3; owning files/interfaces above | AOS-002-TC01, AOS-002-TC02, AOS-002-TC03, AOS-002-TC04; parameterize every condition in this clause |
| AOS-002-F04 | Implement deterministic contract hash via canonical serialization; revision creates a new version and invalidates approval tied to prior digest. DAG validation rejects cycles, self-links and unauthorized project references. | AOS-002-S1, AOS-002-S2, AOS-002-S3; owning files/interfaces above | AOS-002-TC01, AOS-002-TC02, AOS-002-TC03, AOS-002-TC04; parameterize every condition in this clause |
| AOS-002-AC01 | Roundtrip schema and canonical hash property tests; immutable approved version refuses UPDATE; foreign-owner access returns denial. | AOS-002-S1, AOS-002-S2, AOS-002-S3; owning files/interfaces above | AOS-002-TC01, AOS-002-TC02, AOS-002-TC03, AOS-002-TC04; parameterize every condition in this clause |
| AOS-002-AC02 | Concurrent updates same expected version: exactly one wins. DAG cycles and malformed verifier nodes fail admission. Missing/UNKNOWN required check blocks completion. | AOS-002-S1, AOS-002-S2, AOS-002-S3; owning files/interfaces above | AOS-002-TC01, AOS-002-TC02, AOS-002-TC03, AOS-002-TC04; parameterize every condition in this clause |
| AOS-002-AC03 | Migration applies to empty DB, rejects invalid constraints; documented restore drill; error payloads do not leak private root. | AOS-002-S1, AOS-002-S2, AOS-002-S3; owning files/interfaces above | AOS-002-TC01, AOS-002-TC02, AOS-002-TC03, AOS-002-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-002-S1](cursor/prompts/AOS-002-S1.md) | AOS-001 | Strict GoalContract and seven canonical acceptance variants; canonical monetary/hash serialization and legacy rejection fixtures. | AOS-002-TC01; command/report/exit, immutable evidence and diff |
| [AOS-002-S2](cursor/prompts/AOS-002-S2.md) | AOS-002-S1 | Alembic domain schema, composite owner/project/task/contract constraints, closed states, optimistic versions and append-only contract guards. | AOS-002-TC02; command/report/exit, immutable evidence and diff |
| [AOS-002-S3](cursor/prompts/AOS-002-S3.md) | AOS-002-S2 | Scoped repository/service mutations, DAG validation, idempotency conflict handling and state/event concurrency tests. | AOS-002-TC01, AOS-002-TC02, AOS-002-TC03, AOS-002-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-002-TC01 | contract | `tests/integration/test_aos_002.py::test_contract_hash_and_aliases` | Canonical roundtrip hash stable; edited contract creates new version; raw command, legacy discriminator, bool budget and duplicate check IDs rejected. |
| AOS-002-TC02 | migration | `tests/integration/test_aos_002.py::test_scope_constraints` | Migration applies and restore/reapply works; wrong project/owner/task-contract linkage, orphan attempts and invalid states rejected by SQL. |
| AOS-002-TC03 | integration | `tests/integration/test_aos_002.py::test_concurrent_transition_and_cursor` | Two mutations with same row_version produce one winner; global task/goal cursor commit order and rollback gaps are safe. |
| AOS-002-TC04 | security | `tests/integration/test_aos_002.py::test_foreign_scope_and_mass_assignment` | Foreign goal/read/write returns scoped denial; client approved_by/policy booleans and unknown executable fields rejected. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_002.py --junitxml=evidence/AOS-002.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.
## Additional schema review

Review composite FKs for goal owner/project, task contract/goal, workflow attempt/task and check_run contract/task/attempt/artifact. Verify immutable body/delete triggers and once-only approval metadata. A JSON null verifier type cannot pass a nullable SQL CHECK. Test strict monetary/hash normalization, idempotency body conflict, self/cyclic/foreign-goal edges, state/epoch/size/attempt negatives and expected-version collision. Pydantic-only tests cannot establish these DB invariants.


---

<!-- Source: plans/AOS-003-implementation-plan.md -->

# AOS-003 — DBOS-backed durable single-task execution and recovery: implementation plan

**Release:** R0. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-002. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](testing/TEST_EXECUTION.md) and [source spec](specification/specs/AOS-003.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

An accepted synthetic goal runs through a DBOS workflow and recovers after sudden process death while preserving authoritative task state and auditable events.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/execution/dbos_runtime.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/execution/task_workflow.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/execution/recovery.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/execution/admission.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/repositories/events.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `DurableAdmission.submit(uow, task_id, workflow_id) -> AdmissionReceipt`
- `run_task_workflow(task_id, contract_sha256, attempt_number) -> TaskResult`
- `transition_task_tx(request) -> TransitionReceipt`
- `RecoveryService.recover_pending() -> RecoveryReport`

**Migration ownership:** DBOS-managed schema migrations plus app workflow_link/indexes; never custom writes to DBOS internals.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-003-F01 | Implement a `run_task_workflow(task_id, contract_hash)` whose *workflow body remains replay-deterministic*. All time, random IDs, database I/O, worker spawn, and network calls occur in separately checkpointed steps/transactions. | AOS-003-S1, AOS-003-S2, AOS-003-S3; owning files/interfaces above | AOS-003-TC01, AOS-003-TC02, AOS-003-TC03, AOS-003-TC04; parameterize every condition in this clause |
| AOS-003-F02 | Persist a stable DBOS workflow ID tied to goal/task; repeated start by same key returns prior handle or deliberate conflict. Workflow only runs an authorized current contract version. Use separate schemas in one PostgreSQL database; one datasource transaction/session commits task state, event and durable result. DBOS owns its internal tables. | AOS-003-S1, AOS-003-S2, AOS-003-S3; owning files/interfaces above | AOS-003-TC01, AOS-003-TC02, AOS-003-TC03, AOS-003-TC04; parameterize every condition in this clause |
| AOS-003-F03 | Implement explicit `CREATED→VALIDATING→READY→LEASED→RUNNING→VERIFYING→COMPLETED` happy path and terminal/error states. Add controlled pause, cancellation requested, retry-wait and reconciliation states as modeled; R0 mock activity never uses real external side effects. | AOS-003-S1, AOS-003-S2, AOS-003-S3; owning files/interfaces above | AOS-003-TC01, AOS-003-TC02, AOS-003-TC03, AOS-003-TC04; parameterize every condition in this clause |
| AOS-003-F04 | At process startup create/migrate the approved datasource before DBOS.launch, then use DBOS recovery; read authoritative task state from the same database; do not falsely mark a process gone as completed. | AOS-003-S1, AOS-003-S2, AOS-003-S3; owning files/interfaces above | AOS-003-TC01, AOS-003-TC02, AOS-003-TC03, AOS-003-TC04; parameterize every condition in this clause |
| AOS-003-AC01 | Kill server before transaction commit, after the atomic transaction commit but before the workflow observes its return, and after a non-database step checkpoint; restart and assert final task result and monotonic event stream. | AOS-003-S1, AOS-003-S2, AOS-003-S3; owning files/interfaces above | AOS-003-TC01, AOS-003-TC02, AOS-003-TC03, AOS-003-TC04; parameterize every condition in this clause |
| AOS-003-AC02 | Two concurrent duplicate submissions with same idempotency key produce one logical task; no double artifact. Non-deterministic workflow body test catches bad pattern. | AOS-003-S1, AOS-003-S2, AOS-003-S3; owning files/interfaces above | AOS-003-TC01, AOS-003-TC02, AOS-003-TC03, AOS-003-TC04; parameterize every condition in this clause |
| AOS-003-AC03 | Database unavailable: no speculative state transitions; recover cleanly on reconnect. Uncaught terminal exception becomes FAILED and remains inspectable rather than silently restarting forever. | AOS-003-S1, AOS-003-S2, AOS-003-S3; owning files/interfaces above | AOS-003-TC01, AOS-003-TC02, AOS-003-TC03, AOS-003-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-003-S1](cursor/prompts/AOS-003-S1.md) | AOS-002 | Pin/probe datasource session/isolation/launch and client enqueue-in-transaction; commit admission atomically with app request and scoped workflow ID. | AOS-003-TC01; command/report/exit, immutable evidence and diff |
| [AOS-003-S2](cursor/prompts/AOS-003-S2.md) | AOS-003-S1 | Replay-deterministic task workflow with tracked state/event callbacks and separate external-effect steps; duplicate starts resolve existing identity. | AOS-003-TC02; command/report/exit, immutable evidence and diff |
| [AOS-003-S3](cursor/prompts/AOS-003-S3.md) | AOS-003-S2 | Signal-barrier crash/recovery harness and app+DBOS backup/restore drill; publish recovered/failed diagnostics without speculative completion. | AOS-003-TC01, AOS-003-TC02, AOS-003-TC03, AOS-003-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-003-TC01 | integration | `tests/integration/test_aos_003.py::test_atomic_enqueue_and_duplicate` | Concurrent duplicate requests produce one task/workflow; rollback of admission yields neither task nor enqueue. |
| AOS-003-TC02 | chaos | `tests/integration/test_aos_003.py::test_before_after_commit` | Kill before DB commit rolls back all app writes; kill after tracked commit before return replays one transition/event, no callback side effect. |
| AOS-003-TC03 | chaos | `tests/integration/test_aos_003.py::test_uncommitted_external_step` | Synthetic effect completed but checkpoint response lost is observed/reconciled before repeat; FAILED not swallowed. |
| AOS-003-TC04 | integration | `tests/integration/test_aos_003.py::test_database_restore_and_reconnect` | DB unavailable admits no speculative transitions; consistent app+DBOS restore resumes same IDs and correct authoritative status. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_003.py --junitxml=evidence/AOS-003.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.
## Durable control-flow sketch

API ordinary transaction: request dedupe → immutable goal/contract/tasks → owner-consent state → supported enqueue-in-transaction when executable → events last → commit.

Workflow: validate_contract_tx → acquire_attempt_tx → process_intent_tx → spawn_or_observe_step → process_receipt_tx → collect_step → immutable_metadata_tx → verify_step → checks_tx → approval wait → effect_intent_tx → execute_or_reconcile_step → receipt_tx → finish_tx.

Tracked DB callbacks commit with their result; no network/process/file effect inside them. BEFORE_DB_COMMIT kill leaves no writes. AFTER_DB_COMMIT_BEFORE_RETURN replay has exactly one transition/event. AFTER_EXTERNAL_EFFECT_BEFORE_CHECKPOINT requires observation/reconciliation. Unsupported enqueue API calls require the explicit admission-outbox ADR, never uncoordinated task/enqueue writes.


---

<!-- Source: plans/AOS-004-implementation-plan.md -->

# AOS-004 — Synthetic worker, isolated Git workspace and deterministic verification: implementation plan

**Release:** R0. **Format:** checklist; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-003. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](testing/TEST_EXECUTION.md) and [source spec](specification/specs/AOS-004.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

A single mock worker edits only synthetic test files, emits normalized events, and generates immutable diff/test evidence verified without model judgment.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/brokers/harness/mock.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/sandbox/artifact_ingress.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/verification/registry.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/verification/runner.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/verification/diff.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/verification/artifacts.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `MockWorkerAdapter.start/events/observe/cancel/collect(job)`
- `WorktreeManager.create(task_id, attempt_id, base_sha) -> WorkspaceManifest`
- `TrustedCheckRunner.run(check, candidate_ref, deadline) -> CheckResult`
- `ArtifactIngress.finalize(candidate_output, actor, epoch) -> ArtifactRef`

**Migration ownership:** Artifact/check_run/workspace metadata from kernel schema; add indexes only when justified by this slice.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-004-F01 | Implement WorkerAdapter Protocol `capabilities/validate/start/events/observe/cancel/collect` and a mock adapter with scripted progress, delay, failure and crash modes. | AOS-004-S1, AOS-004-S2, AOS-004-S3; owning files/interfaces above | AOS-004-TC01, AOS-004-TC02, AOS-004-TC03, AOS-004-TC04; parameterize every condition in this clause |
| AOS-004-F02 | Construct a toy Git repository in a temporary root with known initial commit; create a per-attempt `git worktree` under a sandbox-controlled directory, never at user-supplied absolute paths. Do not represent a worktree as a security boundary: R0 is mock-only and has no secrets/network credentials. | AOS-004-S1, AOS-004-S2, AOS-004-S3; owning files/interfaces above | AOS-004-TC01, AOS-004-TC02, AOS-004-TC03, AOS-004-TC04; parameterize every condition in this clause |
| AOS-004-F03 | Trusted test commands reference a reviewed command registry with fixed arguments; capture stdout/stderr with byte limit and timeout. Produce diff path report, test report, artifact hashes and provenance; atomically publish artifacts only for current attempt epoch. | AOS-004-S1, AOS-004-S2, AOS-004-S3; owning files/interfaces above | AOS-004-TC01, AOS-004-TC02, AOS-004-TC03, AOS-004-TC04; parameterize every condition in this clause |
| AOS-004-F04 | A result is accepted iff all required typed acceptance verifiers PASS; worker narrative does not override failing deterministic checks. | AOS-004-S1, AOS-004-S2, AOS-004-S3; owning files/interfaces above | AOS-004-TC01, AOS-004-TC02, AOS-004-TC03, AOS-004-TC04; parameterize every condition in this clause |
| AOS-004-AC01 | Synthetic success produces one modified allowed file, a test PASS and immutable diff with matching hashes. | AOS-004-S1, AOS-004-S2, AOS-004-S3; owning files/interfaces above | AOS-004-TC01, AOS-004-TC02, AOS-004-TC03, AOS-004-TC04; parameterize every condition in this clause |
| AOS-004-AC02 | Failing test, path outside allowlist, symlink escape and timeout never yield COMPLETED. Stale epoch cannot publish candidate artifact. | AOS-004-S1, AOS-004-S2, AOS-004-S3; owning files/interfaces above | AOS-004-TC01, AOS-004-TC02, AOS-004-TC03, AOS-004-TC04; parameterize every condition in this clause |
| AOS-004-AC03 | Cancel a hung mock process: task reports cancellation request and actual termination state distinctly. Rerun same seeded fixture yields deterministic acceptance verdict. | AOS-004-S1, AOS-004-S2, AOS-004-S3; owning files/interfaces above | AOS-004-TC01, AOS-004-TC02, AOS-004-TC03, AOS-004-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-004-S1](cursor/prompts/AOS-004-S1.md) | AOS-003 | Synthetic repo/worktree adapter lifecycle and scripted success/bad-path/hung/crash modes; bounded process handle/output. | AOS-004-TC01; command/report/exit, immutable evidence and diff |
| [AOS-004-S2](cursor/prompts/AOS-004-S2.md) | AOS-004-S1 | Reviewed command registry and independent required test bundle; exact diff checks and immutable artifact ingress outside worker write scope. | AOS-004-TC02; command/report/exit, immutable evidence and diff |
| [AOS-004-S3](cursor/prompts/AOS-004-S3.md) | AOS-004-S2 | False-done/tampered evidence/symlink/timeout/cancel/orphan cleanup fixtures and repeatable synthetic demo receipt. | AOS-004-TC01, AOS-004-TC02, AOS-004-TC03, AOS-004-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-004-TC01 | integration | `tests/integration/test_aos_004.py::test_mock_success_and_repeat` | Same seeded fixture yields same verdict and hashes; worker done creates only a candidate until independent checks pass. |
| AOS-004-TC02 | security | `tests/integration/test_aos_004.py::test_bad_path_and_tampered_checks` | Off-scope path/symlink or altered protected mandatory test bundle fails; new worker tests cannot replace required checks. |
| AOS-004-TC03 | chaos | `tests/integration/test_aos_004.py::test_hung_process_and_output` | Wall watchdog times out silent process, drains bounded streams and confirms process group termination or UNKNOWN. |
| AOS-004-TC04 | chaos | `tests/integration/test_aos_004.py::test_artifact_partial_publish` | Corrupt/partial blob denied; crash after finalize before DB ref leaves only a recoverable orphan, never passed evidence. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_004.py --junitxml=evidence/AOS-004.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.


---

<!-- Source: plans/AOS-005-implementation-plan.md -->

# AOS-005 — Minimal goal/approval API and CLI end-to-end synthetic slice: implementation plan

**Release:** R0. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-003, AOS-004. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](testing/TEST_EXECUTION.md) and [source spec](specification/specs/AOS-005.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

A user can submit a synthetic goal, observe authoritative progress, review exact evidence, approve or deny a bound action, and recover across server restart.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/api/auth.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/api/routes/goals.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/api/routes/approvals.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/api/routes/events.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/api/routes/artifacts.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/cli/goals.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/cli/approvals.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/approvals.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `ApprovalService.decide(actor, approval_id, effect_digest, expected_version, decision) -> DecisionReceipt`
- `GoalQueries.get(actor, goal_id) -> GoalView`
- `EventRepository.after(actor, goal_id, seq, limit) -> EventPage`
- `ArtifactService.read(actor, artifact_id) -> VerifiedArtifact`

**Migration ownership:** Approval decision/consumption/idempotency and local session metadata; explicit scoped synthetic owner/project seed.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-005-F01 | FastAPI endpoints `/v1/goals`, `/v1/goals/{id}`, `/v1/goals/{id}/events`, `/v1/artifacts/{id}`, `/v1/approvals`, `/v1/approvals/{id}/decision`, `/v1/goals/{id}/cancel`, plus loopback-only health. | AOS-005-S1, AOS-005-S2, AOS-005-S3; owning files/interfaces above | AOS-005-TC01, AOS-005-TC02, AOS-005-TC03, AOS-005-TC04; parameterize every condition in this clause |
| AOS-005-F02 | CLI: `agentos goal submit --contract path.yaml`, `goal status`, `goal events`, `approve <id>`, `deny <id>`, `artifact show`, `goal cancel`, `r0-demo`. CLI accepts explicit goal id and prints artifact hashes and check verdicts, never hidden approvals. | AOS-005-S1, AOS-005-S2, AOS-005-S3; owning files/interfaces above | AOS-005-TC01, AOS-005-TC02, AOS-005-TC03, AOS-005-TC04; parameterize every condition in this clause |
| AOS-005-F03 | Approval binds exact action kind, effect_digest, owner/project, policy version and expiration. Deduplicate decisions; rejected/expired approvals do not execute. The approval UI is terminal-first for R0; web can be a read-only minimal view. | AOS-005-S1, AOS-005-S2, AOS-005-S3; owning files/interfaces above | AOS-005-TC01, AOS-005-TC02, AOS-005-TC03, AOS-005-TC04; parameterize every condition in this clause |
| AOS-005-F04 | Persist event cursors for replay; HTTP local auth must be sufficient to prevent arbitrary local processes and browser-origin attacks, hardened further by AOS-009 before real access. | AOS-005-S1, AOS-005-S2, AOS-005-S3; owning files/interfaces above | AOS-005-TC01, AOS-005-TC02, AOS-005-TC03, AOS-005-TC04; parameterize every condition in this clause |
| AOS-005-AC01 | A fresh environment runs `make r0-demo`; CLI creates goal, shows RUNNING, returns verifier result, requests approval, and moves to COMPLETED only after approved synthetic action. | AOS-005-S1, AOS-005-S2, AOS-005-S3; owning files/interfaces above | AOS-005-TC01, AOS-005-TC02, AOS-005-TC03, AOS-005-TC04; parameterize every condition in this clause |
| AOS-005-AC02 | Kill API before approval, restart, decide once: exact action executes once in mock; altered effect_digest/expired request denied. Wrong project/owner/task linkage fails the database constraints and service guards; an unauthorized minimum actor cannot decide or consume the request. | AOS-005-S1, AOS-005-S2, AOS-005-S3; owning files/interfaces above | AOS-005-TC01, AOS-005-TC02, AOS-005-TC03, AOS-005-TC04; parameterize every condition in this clause |
| AOS-005-AC03 | HTTP from unauthorized origin and wrong Host denied in basic test; AOS-009 later completes browser/DNS rebinding adversarial matrix. | AOS-005-S1, AOS-005-S2, AOS-005-S3; owning files/interfaces above | AOS-005-TC01, AOS-005-TC02, AOS-005-TC03, AOS-005-TC04; parameterize every condition in this clause |
| AOS-005-AC04 | CLI sees correct state after reconnect, including canonical event cursor and artifact SHA256. | AOS-005-S1, AOS-005-S2, AOS-005-S3; owning files/interfaces above | AOS-005-TC01, AOS-005-TC02, AOS-005-TC03, AOS-005-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-005-S1](cursor/prompts/AOS-005-S1.md) | AOS-003, AOS-004 | Minimal authenticated loopback routes and schema-derived CLI; safe errors/body limits/scoped reads and typed replay. | AOS-005-TC01; command/report/exit, immutable evidence and diff |
| [AOS-005-S2](cursor/prompts/AOS-005-S2.md) | AOS-005-S1 | Immutable action preview/digest, locked approve/deny/expire decisions and continuation_kind contract-vs-merge waits. | AOS-005-TC02; command/report/exit, immutable evidence and diff |
| [AOS-005-S3](cursor/prompts/AOS-005-S3.md) | AOS-005-S2 | Full R0 journey through contract consent, mock candidate, independent evidence and approved synthetic CAS effect; restart/deny/stale paths. | AOS-005-TC01, AOS-005-TC02, AOS-005-TC03, AOS-005-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-005-TC01 | e2e | `tests/e2e/test_aos_005.py::test_r0_positive_journey` | CLI submits and consents, observes task/evidence, approves exact candidate and sees completed synthetic goal after confirmed effect. |
| AOS-005-TC02 | security | `tests/e2e/test_aos_005.py::test_approval_digest_actor_expiry` | Wrong actor/project/digest, expired request or changed payload cannot dispatch effect; unknown check prevents completion. |
| AOS-005-TC03 | integration | `tests/e2e/test_aos_005.py::test_decision_race_idempotency` | Approve/deny and duplicate consume races yield one decision/effect; repeated key with changed body conflicts. |
| AOS-005-TC04 | chaos | `tests/e2e/test_aos_005.py::test_wait_restart_continuation` | Restart at contract wait dispatches only after consent; restart at merge wait resumes finalize, does not launch another worker. |

After tests exist, baseline command is `uv run --frozen pytest tests/e2e/test_aos_005.py --junitxml=evidence/AOS-005.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.
## Decision versus dispatch

The POST decision handler locks/scopes the current request and records one exact digest/actor/expiry verdict/event. A separate durable continuation rechecks evidence/policy and consumes it into one effect intent. UI retries return the same receipt, not duplicate work. Test contract-consent wait and merge wait separately with continuation_kind. Cancellation can stop admissions immediately while an in-flight effect remains UNKNOWN; terminal state cannot be invented.


---

<!-- Source: plans/AOS-006-implementation-plan.md -->

# AOS-006 — Lease fencing, retry bounds, outbox and external-action reconciliation: implementation plan

**Release:** R1. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-003. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](testing/TEST_EXECUTION.md) and [source spec](specification/specs/AOS-006.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

A lost or stale worker cannot publish results, and ambiguous remote effects are reconciled instead of blindly retried.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/kernel/leases.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/effects.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/budgets.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/execution/outbox.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/execution/recovery.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `LeaseService.acquire(uow, task_id, adapter, expected_version) -> AttemptLease`
- `LeaseService.heartbeat(actor, attempt_id, epoch) -> LeaseReceipt`
- `SideEffectService.prepare(actor, intent, approval_id) -> EffectRef`
- `EffectExecutor.reconcile(effect_ref) -> Confirmed|NoEffect|Unknown`

**Migration ownership:** 0002_policy_effects: lease expiry/status, side_effect/outbox/approval_consumption/budget reservations and unique stable effect keys.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-006-F01 | Lease epoch monotonic per task, compare-and-swap transition on epoch; heartbeat TTL and abandoned-attempt reclamation with recovery record. | AOS-006-S1, AOS-006-S2, AOS-006-S3; owning files/interfaces above | AOS-006-TC01, AOS-006-TC02, AOS-006-TC03, AOS-006-TC04; parameterize every condition in this clause |
| AOS-006-F02 | Append outbox intent and side-effect idempotency key in DB transaction before dispatch. Classify effects as read-only, idempotent-with-key, reconcile-by-query, compensatable, or non-retryable. | AOS-006-S1, AOS-006-S2, AOS-006-S3; owning files/interfaces above | AOS-006-TC01, AOS-006-TC02, AOS-006-TC03, AOS-006-TC04; parameterize every condition in this clause |
| AOS-006-F03 | On timeout/transport drop mark effect UNKNOWN → RECONCILING; run target query with stable fingerprint before retry; unresolved effects require owner approval. | AOS-006-S1, AOS-006-S2, AOS-006-S3; owning files/interfaces above | AOS-006-TC01, AOS-006-TC02, AOS-006-TC03, AOS-006-TC04; parameterize every condition in this clause |
| AOS-006-F04 | Per-task max attempts, capped exponential backoff plus jitter, retry budget and no hot-loop on 429/denied policies. | AOS-006-S1, AOS-006-S2, AOS-006-S3; owning files/interfaces above | AOS-006-TC01, AOS-006-TC02, AOS-006-TC03, AOS-006-TC04; parameterize every condition in this clause |
| AOS-006-AC01 | Two workers race: stale epoch update refused; heartbeat expiry does not claim external cancellation. | AOS-006-S1, AOS-006-S2, AOS-006-S3; owning files/interfaces above | AOS-006-TC01, AOS-006-TC02, AOS-006-TC03, AOS-006-TC04; parameterize every condition in this clause |
| AOS-006-AC02 | Mock PR created then response lost: exactly one PR recognized after recovery; unqueryable external operation remains paused for approval. | AOS-006-S1, AOS-006-S2, AOS-006-S3; owning files/interfaces above | AOS-006-TC01, AOS-006-TC02, AOS-006-TC03, AOS-006-TC04; parameterize every condition in this clause |
| AOS-006-AC03 | Replay duplicate outbox row does not repeat non-idempotent action; runaway retry max enforced. | AOS-006-S1, AOS-006-S2, AOS-006-S3; owning files/interfaces above | AOS-006-TC01, AOS-006-TC02, AOS-006-TC03, AOS-006-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-006-S1](cursor/prompts/AOS-006-S1.md) | AOS-003 | CAS epoch/attempt leases with DB-clock expiry and heartbeat; release/reclaim fences all stale writes. | AOS-006-TC01; command/report/exit, immutable evidence and diff |
| [AOS-006-S2](cursor/prompts/AOS-006-S2.md) | AOS-006-S1 | Transactional effect intent/outbox and single-use approval consumption; fixed classification/idempotency/receipt interfaces. | AOS-006-TC02; command/report/exit, immutable evidence and diff |
| [AOS-006-S3](cursor/prompts/AOS-006-S3.md) | AOS-006-S2 | Bounded retry/durable backoff and response-loss reconciliation drills; cancelling cannot invent a no-effect receipt. | AOS-006-TC01, AOS-006-TC02, AOS-006-TC03, AOS-006-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-006-TC01 | integration | `tests/integration/test_aos_006.py::test_lease_race_stale_epoch` | One lease winner; old worker completion after expiry/release cannot publish artifacts, state or checks. |
| AOS-006-TC02 | chaos | `tests/integration/test_aos_006.py::test_effect_response_loss` | Mock create succeeds then response is lost; stable receipt query recognizes one effect, no duplicate dispatch. |
| AOS-006-TC03 | security | `tests/integration/test_aos_006.py::test_approval_consume_and_unknown_effect` | Same request consumed once; unqueryable non-idempotent effect stays RECONCILING for owner resolution. |
| AOS-006-TC04 | unit | `tests/integration/test_aos_006.py::test_retry_and_reservation_limits` | Attempts/backoff bounded, authorization/429 failures never hot-loop; concurrent reservations cannot exceed known cash cap. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_006.py --junitxml=evidence/AOS-006.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.


---

<!-- Source: plans/AOS-007-implementation-plan.md -->

# AOS-007 — Independent project trust, data privacy and autonomy policy model: implementation plan

**Release:** R1. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-002. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](testing/TEST_EXECUTION.md) and [source spec](specification/specs/AOS-007.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

Effective authority is the intersection of three independently versioned policy axes, with a denied axis always taking precedence.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/contracts/policy.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/policy/engine.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/policy/labels.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/policy/profiles.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/repositories/policy.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `PolicyEngine.authorize(request, current_context) -> Permit|Deny|ApprovalNeeded`
- `LabelService.derive(source_labels, reviewed_downgrade=None) -> DataLabel`
- `TrustService.promote(actor, project_id, version, gate_manifest) -> ProfileVersion`

**Migration ownership:** 0002_policy_effects: project_trust_profile/project_action_policy/data_label/policy_decision; independent versions and source lineage.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-007-F01 | Project trust profile controls tested runtime envelope (`SYNTHETIC_DEV`, `PERSONAL_SANDBOX`, `TRUSTED_PROJECT`, `HARDENED_WORKSPACE`); promotion needs versioned security test evidence and owner approval. | AOS-007-S1, AOS-007-S2, AOS-007-S3; owning files/interfaces above | AOS-007-TC01, AOS-007-TC02, AOS-007-TC03, AOS-007-TC04; parameterize every condition in this clause |
| AOS-007-F02 | Privacy label flows from source to snippets, embeddings, prompts, derived artifacts and traces; derived joins inherit most restrictive relevant label unless explicit reviewed downgrade. | AOS-007-S1, AOS-007-S2, AOS-007-S3; owning files/interfaces above | AOS-007-TC01, AOS-007-TC02, AOS-007-TC03, AOS-007-TC04; parameterize every condition in this clause |
| AOS-007-F03 | Autonomy policy is per-action (read/edit/tool-install/external-send/spend/merge/delete/policy-change) with observe/suggest/approve-first/act-and-report/act-silently when permitted. | AOS-007-S1, AOS-007-S2, AOS-007-S3; owning files/interfaces above | AOS-007-TC01, AOS-007-TC02, AOS-007-TC03, AOS-007-TC04; parameterize every condition in this clause |
| AOS-007-F04 | Policy engine emits versioned decision, enforcement requirements, denied reasons; neither LLM nor client supplies trusted `approval_granted` booleans. | AOS-007-S1, AOS-007-S2, AOS-007-S3; owning files/interfaces above | AOS-007-TC01, AOS-007-TC02, AOS-007-TC03, AOS-007-TC04; parameterize every condition in this clause |
| AOS-007-AC01 | Property-test every pair of axes; raising trust with same privacy/autonomy does not enable send or egress; privacy downgrade does not grant file write. | AOS-007-S1, AOS-007-S2, AOS-007-S3; owning files/interfaces above | AOS-007-TC01, AOS-007-TC02, AOS-007-TC03, AOS-007-TC04; parameterize every condition in this clause |
| AOS-007-AC02 | Two projects cannot share policy/profile by implicit filesystem path; policy update invalidates stale approval; RESTRICTED→cloud always DENY. | AOS-007-S1, AOS-007-S2, AOS-007-S3; owning files/interfaces above | AOS-007-TC01, AOS-007-TC02, AOS-007-TC03, AOS-007-TC04; parameterize every condition in this clause |
| AOS-007-AC03 | Missing/uncertain classification denies or requests user decision, not silently PUBLIC. | AOS-007-S1, AOS-007-S2, AOS-007-S3; owning files/interfaces above | AOS-007-TC01, AOS-007-TC02, AOS-007-TC03, AOS-007-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-007-S1](cursor/prompts/AOS-007-S1.md) | AOS-002 | Pure closed trust/privacy/autonomy contracts and per-project versioned records; explicit unknown classification. | AOS-007-TC01; command/report/exit, immutable evidence and diff |
| [AOS-007-S2](cursor/prompts/AOS-007-S2.md) | AOS-007-S1 | Deterministic intersection/derived-label propagation and action/destination enforcement outputs; cache keyed by all versions. | AOS-007-TC02; command/report/exit, immutable evidence and diff |
| [AOS-007-S3](cursor/prompts/AOS-007-S3.md) | AOS-007-S2 | Axis/property and cross-project fixtures, stale-approval invalidation and promotion manifest evidence. | AOS-007-TC01, AOS-007-TC02, AOS-007-TC03, AOS-007-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-007-TC01 | unit | `tests/integration/test_aos_007.py::test_independent_axes_matrix` | Vary only trust, privacy or autonomy: unrelated permissions never widen; any DENY dominates approval/permit. |
| AOS-007-TC02 | security | `tests/integration/test_aos_007.py::test_restricted_cloud_and_labels` | Restricted/unknown label never reaches cloud; summaries/embeddings/artifacts inherit restrictive source labels. |
| AOS-007-TC03 | integration | `tests/integration/test_aos_007.py::test_project_versions_and_revocation` | Project A profile cannot authorize B; policy change invalidates pending decision/approval and cached permits. |
| AOS-007-TC04 | security | `tests/integration/test_aos_007.py::test_model_cannot_self_promote` | Model-authored approved/granted flags or profile promotion without gate/owner evidence rejected. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_007.py --junitxml=evidence/AOS-007.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.


---

<!-- Source: plans/AOS-008-implementation-plan.md -->

# AOS-008 — Sandbox profiles, mount validation and enforceable outbound controls: implementation plan

**Release:** R1. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-004, AOS-007. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](testing/TEST_EXECUTION.md) and [source spec](specification/specs/AOS-008.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

Worker filesystem, process, resource and network access are constrained at OS boundaries before any real repository or vendor account is used.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/sandbox/profiles.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/sandbox/docker_runtime.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/sandbox/mounts.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/sandbox/network.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/sandbox/processes.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/sandbox/artifact_ingress.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `SandboxRuntime.create(profile, mounts, network_policy, budget) -> SandboxHandle`
- `SandboxRuntime.verify_effective_policy(handle) -> EnforcementManifest`
- `SandboxRuntime.destroy(handle, expected_identity) -> CleanupReceipt`
- `PinnedEgressGateway.authorize_connect(context, hostname, resolved_ips) -> ConnectionPermit`

**Migration ownership:** Versioned sandbox/capability/enforcement manifest records; protected profile and configuration digests.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-008-F01 | Define `mock-no-network`, `read-only-research`, `scoped-code-edit`, `restricted-offline` profiles with specific mount allowlist, process UID, cgroups/seccomp where supported, destination allowlist, capability flags, CPU/RAM/time bounds. | AOS-008-S1, AOS-008-S2, AOS-008-S3; owning files/interfaces above | AOS-008-TC01, AOS-008-TC02, AOS-008-TC03, AOS-008-TC04; parameterize every condition in this clause |
| AOS-008-F02 | Use Linux namespaces/bubblewrap or Docker with explicit hardening selected by threat model. Worktrees isolated but not trusted as sole security boundary; vendor CLIs may require authorized network egress to their endpoints. | AOS-008-S1, AOS-008-S2, AOS-008-S3; owning files/interfaces above | AOS-008-TC01, AOS-008-TC02, AOS-008-TC03, AOS-008-TC04; parameterize every condition in this clause |
| AOS-008-F03 | Protect against bind mount escapes, symlinks, hardlinks, Git hooks, known private credential paths, `/proc` escapes, shell config and unexpected proxies; test sandbox startup fail-closed. | AOS-008-S1, AOS-008-S2, AOS-008-S3; owning files/interfaces above | AOS-008-TC01, AOS-008-TC02, AOS-008-TC03, AOS-008-TC04; parameterize every condition in this clause |
| AOS-008-F04 | Disallow privileged containers, host Docker socket mounts and broad `$HOME` visibility; separate vendor CLI auth state from untrusted worktree filesystem. | AOS-008-S1, AOS-008-S2, AOS-008-S3; owning files/interfaces above | AOS-008-TC01, AOS-008-TC02, AOS-008-TC03, AOS-008-TC04; parameterize every condition in this clause |
| AOS-008-AC01 | Attempt read `~/.ssh`, `/etc/shadow`, parent of worktree, follow symlink outside root and resolve 127.0.0.1/169.254.169.254: blocked at OS/network boundary. | AOS-008-S1, AOS-008-S2, AOS-008-S3; owning files/interfaces above | AOS-008-TC01, AOS-008-TC02, AOS-008-TC03, AOS-008-TC04; parameterize every condition in this clause |
| AOS-008-AC02 | Network disallowed profile demonstrably cannot open remote or localhost socket; worker cannot mount broader filesystem or launch privileged container. | AOS-008-S1, AOS-008-S2, AOS-008-S3; owning files/interfaces above | AOS-008-TC01, AOS-008-TC02, AOS-008-TC03, AOS-008-TC04; parameterize every condition in this clause |
| AOS-008-AC03 | Sandbox failure means task FAIL/DENY, not unconfined fallback. | AOS-008-S1, AOS-008-S2, AOS-008-S3; owning files/interfaces above | AOS-008-TC01, AOS-008-TC02, AOS-008-TC03, AOS-008-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-008-S1](cursor/prompts/AOS-008-S1.md) | AOS-004, AOS-007 | Concrete Linux Docker profiles and capability probe; non-root/read-only root/caps/process/resource ceilings, explicit mount containment. | AOS-008-TC01; command/report/exit, immutable evidence and diff |
| [AOS-008-S2](cursor/prompts/AOS-008-S2.md) | AOS-008-S1 | Default-deny egress gateway/pinned destination and separate verifier/reader profiles; fail closed on startup/enforcement gaps. | AOS-008-TC02; command/report/exit, immutable evidence and diff |
| [AOS-008-S3](cursor/prompts/AOS-008-S3.md) | AOS-008-S2 | Effective in-sandbox filesystem/network/credential/process attacks and cleanup/conformance report on actual OS. | AOS-008-TC01, AOS-008-TC02, AOS-008-TC03, AOS-008-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-008-TC01 | security | `tests/integration/test_aos_008.py::test_mount_symlink_proc_escape` | Synthetic host credential/parent/proc/device/hardlink targets blocked; no privileged container or docker socket. |
| AOS-008-TC02 | security | `tests/integration/test_aos_008.py::test_network_gateway_escape` | Direct socket/DNS/private/localhost/metadata attempts denied where profile forbids; allowed channel cannot become arbitrary proxy. |
| AOS-008-TC03 | live | `tests/integration/test_aos_008.py::test_os_effective_uid_mounts_egress_and_limits` | Real host process namespace/UID/cgroup/mount/egress probes match manifest and enforce caps; unsupported feature is not PASS. |
| AOS-008-TC04 | chaos | `tests/integration/test_aos_008.py::test_sandbox_failure_cleanup` | Startup failure refuses unconfined fallback; orphan process cleanup uses identity and preserves unrelated workspace. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_008.py --junitxml=evidence/AOS-008.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.


---

<!-- Source: plans/AOS-009-implementation-plan.md -->

# AOS-009 — Loopback API authentication, host/origin hardening and approvals: implementation plan

**Release:** R1. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-005, AOS-007. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](testing/TEST_EXECUTION.md) and [source spec](specification/specs/AOS-009.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

Even local browser pages or untrusted network content cannot submit AgentOS actions, invoke approvals or hijack a localhost API.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/api/auth.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/api/sessions.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/api/csrf.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/api/middleware.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/approvals.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `ActorResolver.resolve(request) -> ActorContext`
- `BrowserSessionService.pair(local_code, origin) -> SessionReceipt`
- `MutationGuard.validate(request, actor, csrf) -> GuardContext`
- `ApprovalService.consume(uow, approval_id, intent) -> ExistingEffect|NewEffect`

**Migration ownership:** Local token/session/pairing metadata, auth revocation and approval consumed binding; secret values stored outside untrusted workspaces.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-009-F01 | Enforce loopback bind, allowlisted Host, trusted Origin, session auth, anti-CSRF on mutations, no wildcard CORS and browser security headers. Detect DNS rebinding via Host validation and trusted origin checks. | AOS-009-S1, AOS-009-S2, AOS-009-S3; owning files/interfaces above | AOS-009-TC01, AOS-009-TC02, AOS-009-TC03, AOS-009-TC04; parameterize every condition in this clause |
| AOS-009-F02 | Approval is exact `(owner, project, task, effect_hash, action, policy_version, expiry)` and single-consumption. Mutating operation checks policy again on execution; approve button never executes a different payload. | AOS-009-S1, AOS-009-S2, AOS-009-S3; owning files/interfaces above | AOS-009-TC01, AOS-009-TC02, AOS-009-TC03, AOS-009-TC04; parameterize every condition in this clause |
| AOS-009-F03 | Rate-limit endpoints and cap body sizes; API content-type/schema validation; prevent cached sensitive artifact responses. Implement non-browser CLI auth without bypassing owner identity. | AOS-009-S1, AOS-009-S2, AOS-009-S3; owning files/interfaces above | AOS-009-TC01, AOS-009-TC02, AOS-009-TC03, AOS-009-TC04; parameterize every condition in this clause |
| AOS-009-F04 | Do not expose remotely except user-configured Tailscale/SSH binding with explicit stronger auth and threat review. | AOS-009-S1, AOS-009-S2, AOS-009-S3; owning files/interfaces above | AOS-009-TC01, AOS-009-TC02, AOS-009-TC03, AOS-009-TC04; parameterize every condition in this clause |
| AOS-009-AC01 | Foreign origin POST, wrong Host, DNS rebinding host, expired and duplicate approval denied. | AOS-009-S1, AOS-009-S2, AOS-009-S3; owning files/interfaces above | AOS-009-TC01, AOS-009-TC02, AOS-009-TC03, AOS-009-TC04; parameterize every condition in this clause |
| AOS-009-AC02 | Contract mutation after approval invalidates old digest; race approving/rejecting has one final result. | AOS-009-S1, AOS-009-S2, AOS-009-S3; owning files/interfaces above | AOS-009-TC01, AOS-009-TC02, AOS-009-TC03, AOS-009-TC04; parameterize every condition in this clause |
| AOS-009-AC03 | Authorized local CLI unaffected; referrer/CSRF bypass tests and websocket/SSE origin cases covered. | AOS-009-S1, AOS-009-S2, AOS-009-S3; owning files/interfaces above | AOS-009-TC01, AOS-009-TC02, AOS-009-TC03, AOS-009-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-009-S1](cursor/prompts/AOS-009-S1.md) | AOS-005, AOS-007 | CLI token/actor storage and exact Host/Origin/body/media/rate middleware; safe same-origin API semantics. | AOS-009-TC01; command/report/exit, immutable evidence and diff |
| [AOS-009-S2](cursor/prompts/AOS-009-S2.md) | AOS-009-S1 | One-use pairing, scoped cookie/session/CSRF and expiry/revoke; no URL tokens or wildcard CORS. | AOS-009-TC02; command/report/exit, immutable evidence and diff |
| [AOS-009-S3](cursor/prompts/AOS-009-S3.md) | AOS-009-S2 | Actual browser/cookie/SSE and stale-decision races with bounded failure/error audit. | AOS-009-TC01, AOS-009-TC02, AOS-009-TC03, AOS-009-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-009-TC01 | security | `tests/integration/test_aos_009.py::test_origin_host_csrf_matrix` | Wrong Host/Origin, forged mutation, missing browser CSRF and expired sessions denied; authenticated CLI missing Origin remains correctly scoped. |
| AOS-009-TC02 | security | `tests/integration/test_aos_009.py::test_pairing_and_secret_redaction` | One-time code rate/expiry/reuse enforced; tokens and pairing content absent from URLs/logs/events. |
| AOS-009-TC03 | integration | `tests/integration/test_aos_009.py::test_approval_decision_consumption_races` | Changed contract/candidate/policy/actor invalidates digest; one approved effect consumed under races. |
| AOS-009-TC04 | e2e | `tests/integration/test_aos_009.py::test_browser_session_revocation` | Revoke session prevents SSE reconnect/artifact access and mutation; UI clears private view without inventing task completion. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_009.py --junitxml=evidence/AOS-009.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.


---

<!-- Source: plans/AOS-010-implementation-plan.md -->

# AOS-010 — Hardened Claude Code worker adapter and hostile-repository tests: implementation plan

**Release:** R1. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-004, AOS-008, AOS-009. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](testing/TEST_EXECUTION.md) and [source spec](specification/specs/AOS-010.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

One official Claude Code worker can perform a bounded, authorized code task without executing hostile repository-provided hooks, MCP servers, or plugin initialization.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/brokers/harness/claude.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/brokers/harness/event_parser.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/brokers/harness/process_runner.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/sandbox/native_tool_gateway.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/memory/context.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `ClaudeCodeAdapter.validate/start/events/observe/cancel/collect(job)`
- `CliProfileProbe.inspect(binary_ref, auth_handle, effective_config) -> CompatibilityManifest`
- `NativeToolGateway.execute(reviewed_request, scope, deadline) -> ToolReceipt`

**Migration ownership:** Adapter/version/profile/auth-mode/consent metadata; no token serialization or credential table.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-010-F01 | Inventory and validate any existing `claude-code-worker` skill. Pin Claude CLI version and auto-updater policy; probe `claude auth status` without extracting credentials. | AOS-010-S1, AOS-010-S2, AOS-010-S3; owning files/interfaces above | AOS-010-TC01, AOS-010-TC02, AOS-010-TC03, AOS-010-TC04; parameterize every condition in this clause |
| AOS-010-F02 | Implement subscription-compatible startup profiles. Test `--safe-mode` for disabling project customizations; it may ignore `CLAUDE.md`, so trusted context enters via documented prompt-file interface. Evaluate `--restricted` against the pinned build and explicit tool list; fallback to controlled `--setting-sources`, `--settings`, `--strict-mcp-config` only if behavior proven. `--bare` is API-only; do not imply subscription access. | AOS-010-S1, AOS-010-S2, AOS-010-S3; owning files/interfaces above | AOS-010-TC01, AOS-010-TC02, AOS-010-TC03, AOS-010-TC04; parameterize every condition in this clause |
| AOS-010-F03 | Use dedicated Claude config directory owned by user; worker sees only scope-necessary CLI state; sandbox-protect from repo contents. Explicit permission mode, no interactive prompt expectation, max turns/wall time, runtime cancel/status semantics. | AOS-010-S1, AOS-010-S2, AOS-010-S3; owning files/interfaces above | AOS-010-TC01, AOS-010-TC02, AOS-010-TC03, AOS-010-TC04; parameterize every condition in this clause |
| AOS-010-F04 | Parse versioned streamed JSON defensively; normalize events; fail closed on unknown event/privilege request or missing auth. Disable auto-execution from `.claude/`, `.mcp.json` and `.claude/settings.json` on test fixture. | AOS-010-S1, AOS-010-S2, AOS-010-S3; owning files/interfaces above | AOS-010-TC01, AOS-010-TC02, AOS-010-TC03, AOS-010-TC04; parameterize every condition in this clause |
| AOS-010-AC01 | Malicious `SessionStart` and `PreToolUse` hooks and MCP definitions with exfil sentinel never execute. | AOS-010-S1, AOS-010-S2, AOS-010-S3; owning files/interfaces above | AOS-010-TC01, AOS-010-TC02, AOS-010-TC03, AOS-010-TC04; parameterize every condition in this clause |
| AOS-010-AC02 | Safe-mode context comes through approved prompt file, not ignored workspace `CLAUDE.md`; scope of safe/restricted modes confirmed against installed CLI. | AOS-010-S1, AOS-010-S2, AOS-010-S3; owning files/interfaces above | AOS-010-TC01, AOS-010-TC02, AOS-010-TC03, AOS-010-TC04; parameterize every condition in this clause |
| AOS-010-AC03 | No-tools mode cannot call shell; Build profile explicitly permits bounded Bash inside sandbox; auth-required and quota errors handled without retry storm. | AOS-010-S1, AOS-010-S2, AOS-010-S3; owning files/interfaces above | AOS-010-TC01, AOS-010-TC02, AOS-010-TC03, AOS-010-TC04; parameterize every condition in this clause |
| AOS-010-AC04 | Cancel/timeout produces correct status; structured-output schema fixture tests cover partial/truncated JSON. | AOS-010-S1, AOS-010-S2, AOS-010-S3; owning files/interfaces above | AOS-010-TC01, AOS-010-TC02, AOS-010-TC03, AOS-010-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-010-S1](cursor/prompts/AOS-010-S1.md) | AOS-004, AOS-008, AOS-009 | Inspect original skill, pin/probe official CLI/auth/config/profile semantics and sanitized event fixture parser; no live auth provisioning. | AOS-010-TC01; command/report/exit, immutable evidence and diff |
| [AOS-010-S2](cursor/prompts/AOS-010-S2.md) | AOS-010-S1 | Bounded process lifecycle/context-file launch with edited workspace and tested credential/tool separation; shell-tier spike remains explicit. | AOS-010-TC02; command/report/exit, immutable evidence and diff |
| [AOS-010-S3](cursor/prompts/AOS-010-S3.md) | AOS-010-S2 | Hostile hooks/MCP/config, silent timeout/cancel/partial JSON fixtures plus separately consented synthetic live compatibility smoke. | AOS-010-TC01, AOS-010-TC02, AOS-010-TC03, AOS-010-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-010-TC01 | contract | `tests/integration/test_aos_010.py::test_claude_json_errors` | Sanitized success/auth/quota/truncated/malformed/unknown state-bearing events normalize or fail safely; candidate is never kernel completion. |
| AOS-010-TC02 | security | `tests/integration/test_aos_010.py::test_hostile_repo_configs` | Malicious SessionStart/PreToolUse/settings/MCP sentinels never run; inherited/managed unexpected configuration refuses certification. |
| AOS-010-TC03 | live | `tests/integration/test_aos_010.py::test_claude_modes_auth_tool_isolation` | Exact CLI/auth/profile combination supports scoped task/context; synthetic credential outside tool scope unreadable; enabled Bash tier requires OS gateway proof. |
| AOS-010-TC04 | chaos | `tests/integration/test_aos_010.py::test_claude_silent_timeout_cancel` | Watchdog fires even with no stdout, bounded process group shutdown reported accurately and lost start receipt reconciled. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_010.py --junitxml=evidence/AOS-010.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.


---

<!-- Source: plans/AOS-027a-implementation-plan.md -->

# AOS-027a — Single-worker verification and protected merge approval: implementation plan

**Release:** R1. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-004, AOS-009, AOS-010. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](testing/TEST_EXECUTION.md) and [source spec](specification/specs/AOS-027a.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

One worker candidate is independently verified and can merge only with an exact scoped effect_digest-bound approval.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/verification/runner.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/verification/diff.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/verification/merge.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/approvals.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/effects.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `VerificationService.verify_candidate(actor, candidate_ref, contract_id) -> BuildEvidenceBundle`
- `MergeApprovalService.request(actor, evidence, destination_ref) -> ApprovalPreview`
- `ProtectedGitActor.compare_and_swap(effect) -> MergeReceipt`

**Migration ownership:** Candidate/base/tree/check-set hashes and evidence-bound effect/approval indexes; retain single-worker protocol before concurrency.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-027a-F01 | Implement the R1 single-worker verifier and merge-approval service after AOS-004, AOS-009 and AOS-010. Use canonical trusted-command-ref, git-diff-path-check and policy-decision checks; human-review evidence cannot substitute for explicit action authorization. | AOS-027a-S1, AOS-027a-S2, AOS-027a-S3; owning files/interfaces above | AOS-027a-TC01, AOS-027a-TC02, AOS-027a-TC03, AOS-027a-TC04; parameterize every condition in this clause |
| AOS-027a-F02 | Verifier must run against the **candidate final tree** for the single worker and exact intended destination base; a stale worktree test report cannot authorize a changed candidate. Use pinned known test commands with timeout and output limit; file diff signed with commit/tree SHA. | AOS-027a-S1, AOS-027a-S2, AOS-027a-S3; owning files/interfaces above | AOS-027a-TC01, AOS-027a-TC02, AOS-027a-TC03, AOS-027a-TC04; parameterize every condition in this clause |
| AOS-027a-F03 | Protected merge requires approval digest binding exact candidate commit, destination branch, check set, project/action policy version and expiry. Revalidate immediately before side effect; unexpected external effect goes RECONCILING. | AOS-027a-S1, AOS-027a-S2, AOS-027a-S3; owning files/interfaces above | AOS-027a-TC01, AOS-027a-TC02, AOS-027a-TC03, AOS-027a-TC04; parameterize every condition in this clause |
| AOS-027a-F04 | Missing evidence, failed/UNKNOWN checks, modified diff after approval or policy mismatch means no merge. | AOS-027a-S1, AOS-027a-S2, AOS-027a-S3; owning files/interfaces above | AOS-027a-TC01, AOS-027a-TC02, AOS-027a-TC03, AOS-027a-TC04; parameterize every condition in this clause |
| AOS-027a-AC01 | Deliberately failing tests reject worker 'done'; unauthorized path diff rejects before completion. | AOS-027a-S1, AOS-027a-S2, AOS-027a-S3; owning files/interfaces above | AOS-027a-TC01, AOS-027a-TC02, AOS-027a-TC03, AOS-027a-TC04; parameterize every condition in this clause |
| AOS-027a-AC02 | Rebase changes candidate hash: old approval invalid. Inject lost response after mock merge: no duplicate merge; unresolved state requires reconciliation. | AOS-027a-S1, AOS-027a-S2, AOS-027a-S3; owning files/interfaces above | AOS-027a-TC01, AOS-027a-TC02, AOS-027a-TC03, AOS-027a-TC04; parameterize every condition in this clause |
| AOS-027a-AC03 | One hardened Claude Code worker produces a candidate, verifier independently checks it, and a single-use effect_digest-bound approval permits only that exact scoped merge. Wrong owner/project, changed destination/base/candidate/check set or expired approval denies execution. | AOS-027a-S1, AOS-027a-S2, AOS-027a-S3; owning files/interfaces above | AOS-027a-TC01, AOS-027a-TC02, AOS-027a-TC03, AOS-027a-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-027a-S1](cursor/prompts/AOS-027a-S1.md) | AOS-004, AOS-009, AOS-010 | Independent protected command/check bundle on exact single-worker candidate; allowed/forbidden diff and artifact/verifier hashes. | AOS-027a-TC01; command/report/exit, immutable evidence and diff |
| [AOS-027a-S2](cursor/prompts/AOS-027a-S2.md) | AOS-027a-S1 | Effect_digest preview includes owner/project/base/destination/check/policy/expiry; one-use consumption and protected ref CAS. | AOS-027a-TC02; command/report/exit, immutable evidence and diff |
| [AOS-027a-S3](cursor/prompts/AOS-027a-S3.md) | AOS-027a-S2 | False done, tampered tests, changed base/rebase, lost merge response and single-worker gate report. | AOS-027a-TC01, AOS-027a-TC02, AOS-027a-TC03, AOS-027a-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-027a-TC01 | security | `tests/integration/test_aos_027a.py::test_worker_cannot_weaken_checks` | Failing required test, unauthorized diff or replaced trusted bundle prevents completion/approval regardless of worker narrative. |
| AOS-027a-TC02 | integration | `tests/integration/test_aos_027a.py::test_exact_candidate_cas_approval` | Only approved current candidate can update protected ref from expected base; wrong project/base/branch/check hash rejects. |
| AOS-027a-TC03 | chaos | `tests/integration/test_aos_027a.py::test_merge_receipt_loss` | Crash after ref CAS before receipt is confirmed by stable reconciliation, without second merge or stale worker dispatch. |
| AOS-027a-TC04 | live | `tests/integration/test_aos_027a.py::test_single_worker_verified_build` | One certified Claude worker produces a bounded synthetic patch, independent tests and explicit exact merge approval with observed receipts. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_027a.py --junitxml=evidence/AOS-027a.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.


---

<!-- Source: plans/AOS-011-implementation-plan.md -->

# AOS-011 — Source-linked personal memory schema and five-stage use events: implementation plan

**Release:** R1. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-002. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](testing/TEST_EXECUTION.md) and [source spec](specification/specs/AOS-011.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

Offline Ask can retrieve owner/project-scoped memory with provenance, while every retrieval stage creates audit-ready data for later measurable personalization.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/memory/store.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/memory/search.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/memory/use_events.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/memory/context.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/memory/lifecycle.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/repositories/memory.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `MemoryStore.add_or_revise(actor, source, fact, expected_revision) -> MemoryRevision`
- `MemorySearch.retrieve(actor, query, limit, now) -> ProvenanceResults`
- `MemoryUseRecorder.record(observer, stage, context_ref, confidence) -> UseEvent`
- `MemoryLifecycle.suppress(actor, memory_id) -> SuppressionReceipt`

**Migration ownership:** 0003_memory: memory_item/source/revision/use_event/context_pack with scope, labels, validity, pin, suppression, retention and FTS index.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-011-F01 | Create normalized `memory_item`, `memory_source`, `memory_revision`, `memory_use_event` and optional `context_pack` tables, owner/project/privacy/provenance/validity and retention fields. R1 starts with PostgreSQL full-text search, deterministic ranking baseline; pgvector optional with model-version metadata. | AOS-011-S1, AOS-011-S2, AOS-011-S3; owning files/interfaces above | AOS-011-TC01, AOS-011-TC02, AOS-011-TC03, AOS-011-TC04; parameterize every condition in this clause |
| AOS-011-F02 | Record distinct `retrieved`, `included`, `used_by_worker`, `judged_unused`, `candidate_helped` stages with source/observer/confidence; do not auto-equate inclusion with use or successful task with causality. | AOS-011-S1, AOS-011-S2, AOS-011-S3; owning files/interfaces above | AOS-011-TC01, AOS-011-TC02, AOS-011-TC03, AOS-011-TC04; parameterize every condition in this clause |
| AOS-011-F03 | Restrict memory writes to user-submitted facts or verified explicit task outputs in R1; model-inferred changes proposed for approval. No automatic deletion based on unvalidated utility score. | AOS-011-S1, AOS-011-S2, AOS-011-S3; owning files/interfaces above | AOS-011-TC01, AOS-011-TC02, AOS-011-TC03, AOS-011-TC04; parameterize every condition in this clause |
| AOS-011-F04 | Protect memory from cross-owner/project leakage through application checks and, if feasible, PostgreSQL row-level security tests. Retrieval returns source IDs and relevance explanations. | AOS-011-S1, AOS-011-S2, AOS-011-S3; owning files/interfaces above | AOS-011-TC01, AOS-011-TC02, AOS-011-TC03, AOS-011-TC04; parameterize every condition in this clause |
| AOS-011-AC01 | Query returns correct project-local preference and evidence; another project's secret cannot appear, even through semantic similarity. | AOS-011-S1, AOS-011-S2, AOS-011-S3; owning files/interfaces above | AOS-011-TC01, AOS-011-TC02, AOS-011-TC03, AOS-011-TC04; parameterize every condition in this clause |
| AOS-011-AC02 | Five event stages each persist and survive restart, including explicit judged-unused; nonobserved stages remain unknown rather than inferred. | AOS-011-S1, AOS-011-S2, AOS-011-S3; owning files/interfaces above | AOS-011-TC01, AOS-011-TC02, AOS-011-TC03, AOS-011-TC04; parameterize every condition in this clause |
| AOS-011-AC03 | Invalid/superseded facts suppressed from current recall but lineage preserved; injection in retrieved content never upgrades policy. | AOS-011-S1, AOS-011-S2, AOS-011-S3; owning files/interfaces above | AOS-011-TC01, AOS-011-TC02, AOS-011-TC03, AOS-011-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-011-S1](cursor/prompts/AOS-011-S1.md) | AOS-002 | Normalized source-linked memory/revisions with immutable provenance and explicit owner-approved writes. | AOS-011-TC01; command/report/exit, immutable evidence and diff |
| [AOS-011-S2](cursor/prompts/AOS-011-S2.md) | AOS-011-S1 | Scoped FTS retrieval/validity/conflict ranking and minimal hashed context packs with bounded tokens; unknown stages remain unknown. | AOS-011-TC02; command/report/exit, immutable evidence and diff |
| [AOS-011-S3](cursor/prompts/AOS-011-S3.md) | AOS-011-S2 | Five-stage telemetry, correction/export/suppression/retention baseline and cross-project/injection/stale-memory fixtures. | AOS-011-TC01, AOS-011-TC02, AOS-011-TC03, AOS-011-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-011-TC01 | integration | `tests/integration/test_aos_011.py::test_scoped_valid_fact_recall` | Project preference returns exact source/current revision; expired, superseded and suppressed facts absent before ranking. |
| AOS-011-TC02 | security | `tests/integration/test_aos_011.py::test_cross_project_injection` | Other owner/project data never appears; memory content cannot change policy, provider route or standing rules. |
| AOS-011-TC03 | contract | `tests/integration/test_aos_011.py::test_five_stages_unknown_attribution` | Five distinct stages persist with observer/confidence; inclusion/success never invent used/helped causality. |
| AOS-011-TC04 | integration | `tests/integration/test_aos_011.py::test_revision_suppression_restore` | Correction creates new revision; pins retained; suppression blocks new contexts and DB restore retains lineage/suppression metadata. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_011.py --junitxml=evidence/AOS-011.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.


---

<!-- Source: plans/AOS-012-implementation-plan.md -->

# AOS-012 — Routing outcomes, corrections and cloud-exposure event contracts: implementation plan

**Release:** R1. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-002, AOS-007. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](testing/TEST_EXECUTION.md) and [source spec](specification/specs/AOS-012.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

Every future routing/personalization decision has minimally sufficient evidence from the earliest real tasks, without claiming unavailable cost/quota data.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/telemetry/usage.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/telemetry/exposure.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/repositories/routing.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/memory/use_events.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `RoutingRecorder.decision(actor, candidates, selected, policy_ref) -> RouteRef`
- `OutcomeRecorder.record(task_ref, verifier_refs, correction_ref) -> OutcomeRef`
- `ExposureLedger.record_authorized/accessible/observed(scope, record) -> ExposureRef`

**Migration ownership:** 0004_telemetry: routing_decision/outcome/user_correction/exposure_observation/usage_observation with nullable unknown measurements.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-012-F01 | Persist eligible/denied backend candidates, reason, capability class, policy IDs, selected route, expected cost/risk and uncertainty; post-execution task outcome references deterministic verifier/user acceptance. | AOS-012-S1, AOS-012-S2, AOS-012-S3; owning files/interfaces above | AOS-012-TC01, AOS-012-TC02, AOS-012-TC03, AOS-012-TC04; parameterize every condition in this clause |
| AOS-012-F02 | Record `user_correction` as diff/rejection/explicit text with output version, owner consent and sensitivity. Do not train or infer preferences merely from passive prompt data. | AOS-012-S1, AOS-012-S2, AOS-012-S3; owning files/interfaces above | AOS-012-TC01, AOS-012-TC02, AOS-012-TC03, AOS-012-TC04; parameterize every condition in this clause |
| AOS-012-F03 | Store three separate outbound-data dimensions: `authorized` (policy), `accessible` (files/prompt scope), `observed` (OS/process network metadata); encrypted CLI contents may be unknowable. | AOS-012-S1, AOS-012-S2, AOS-012-S3; owning files/interfaces above | AOS-012-TC01, AOS-012-TC02, AOS-012-TC03, AOS-012-TC04; parameterize every condition in this clause |
| AOS-012-F04 | Cost and quota observations use `known/estimated/unknown` with null amount for unknown; event schemas are versioned for eventual subscriptions optimizer. | AOS-012-S1, AOS-012-S2, AOS-012-S3; owning files/interfaces above | AOS-012-TC01, AOS-012-TC02, AOS-012-TC03, AOS-012-TC04; parameterize every condition in this clause |
| AOS-012-AC01 | After process restart reconstruct route selection and rejection reasons from DB alone. | AOS-012-S1, AOS-012-S2, AOS-012-S3; owning files/interfaces above | AOS-012-TC01, AOS-012-TC02, AOS-012-TC03, AOS-012-TC04; parameterize every condition in this clause |
| AOS-012-AC02 | Unknown quota yields null, not 0 or unlimited; possible egress reported accessible but not observed with correct distinction. | AOS-012-S1, AOS-012-S2, AOS-012-S3; owning files/interfaces above | AOS-012-TC01, AOS-012-TC02, AOS-012-TC03, AOS-012-TC04; parameterize every condition in this clause |
| AOS-012-AC03 | User correction cannot overwrite immutable original answer artifact; denied route remains denied after another agent suggests it. | AOS-012-S1, AOS-012-S2, AOS-012-S3; owning files/interfaces above | AOS-012-TC01, AOS-012-TC02, AOS-012-TC03, AOS-012-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-012-S1](cursor/prompts/AOS-012-S1.md) | AOS-002, AOS-007 | Versioned eligible/denied route and normalized usage/outcome schemas linked to task/policy/correlation. | AOS-012-TC01; command/report/exit, immutable evidence and diff |
| [AOS-012-S2](cursor/prompts/AOS-012-S2.md) | AOS-012-S1 | Separate authorized/accessible/observed disclosure records, corrected output versions and consent/retention boundaries. | AOS-012-TC02; command/report/exit, immutable evidence and diff |
| [AOS-012-S3](cursor/prompts/AOS-012-S3.md) | AOS-012-S2 | Restart reconstruction, unknown-value and poisoned-correction fixtures; secret-safe API/report views. | AOS-012-TC01, AOS-012-TC02, AOS-012-TC03, AOS-012-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-012-TC01 | contract | `tests/integration/test_aos_012.py::test_usage_unknown_not_zero` | Unknown amount/quota remains null with confidence status; native plan allowance and API cash distinct. |
| AOS-012-TC02 | integration | `tests/integration/test_aos_012.py::test_routing_replay_restart` | DB alone reconstructs selected route and every rejection reason after process restart. |
| AOS-012-TC03 | security | `tests/integration/test_aos_012.py::test_correction_is_not_authority` | Correction cannot overwrite original evidence or permit denied route; model suggestion cannot manufacture consent. |
| AOS-012-TC04 | contract | `tests/integration/test_aos_012.py::test_exposure_three_dimensions` | Accessible encrypted CLI workspace is not claimed actually transmitted; observed network metadata and authorized policy are separately recorded. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_012.py --junitxml=evidence/AOS-012.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.


---

<!-- Source: plans/AOS-014-implementation-plan.md -->

# AOS-014 — OpenTelemetry correlation, canonical event replay and SSE: implementation plan

**Release:** R1. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-003, AOS-012. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](testing/TEST_EXECUTION.md) and [source spec](specification/specs/AOS-014.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

Trace and UI streams explain every decision without becoming the source of task truth; disconnected clients can replay missed events reliably.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/telemetry/events.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/telemetry/tracing.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/telemetry/redaction.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/api/routes/events.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/repositories/events.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `OrderedEventWriter.append_last(uow, events) -> PersistedEvents`
- `EventRepository.after(actor, goal_id, after_seq, page_size) -> EventPage`
- `SSESerializer.encode(event) -> Bytes`
- `TraceContext.attach(goal, task, attempt, policy) -> Correlation`

**Migration ownership:** task_event indexes and safe audit/trace metadata from kernel/telemetry migrations; seq schema already locked, not reopened.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-014-F01 | Add OpenTelemetry instrumentation to API, kernel, DBOS step, worker adapter and verifier, using propagated trace IDs and task/attempt correlation IDs. Never export content by default. | AOS-014-S1, AOS-014-S2, AOS-014-S3; owning files/interfaces above | AOS-014-TC01, AOS-014-TC02, AOS-014-TC03, AOS-014-TC04; parameterize every condition in this clause |
| AOS-014-F02 | Canonical events persisted in DB before fanout; event cursor monotonically ordered and stable across restart. SSE supports reconnect and `Last-Event-ID` with scoped ownership/authorization. | AOS-014-S1, AOS-014-S2, AOS-014-S3; owning files/interfaces above | AOS-014-TC01, AOS-014-TC02, AOS-014-TC03, AOS-014-TC04; parameterize every condition in this clause |
| AOS-014-F03 | Audit events retain actor, policy decision ID, effect ID, event digest and optional hash-chain reference; privacy-aware structured logging with sensitive fields redacted. | AOS-014-S1, AOS-014-S2, AOS-014-S3; owning files/interfaces above | AOS-014-TC01, AOS-014-TC02, AOS-014-TC03, AOS-014-TC04; parameterize every condition in this clause |
| AOS-014-F04 | Phoenix export optional at R1, required by R3 if it still meets footprint. Unknown model usage logs as unknown. | AOS-014-S1, AOS-014-S2, AOS-014-S3; owning files/interfaces above | AOS-014-TC01, AOS-014-TC02, AOS-014-TC03, AOS-014-TC04; parameterize every condition in this clause |
| AOS-014-AC01 | Disconnect SSE after N events and reconnect: receive every unique event, no false completion; duplicate delivery safe. | AOS-014-S1, AOS-014-S2, AOS-014-S3; owning files/interfaces above | AOS-014-TC01, AOS-014-TC02, AOS-014-TC03, AOS-014-TC04; parameterize every condition in this clause |
| AOS-014-AC02 | Trace ID joins API→DBOS→adapter→verifier; secret sentinel never appears in JSON event or Phoenix exporter. | AOS-014-S1, AOS-014-S2, AOS-014-S3; owning files/interfaces above | AOS-014-TC01, AOS-014-TC02, AOS-014-TC03, AOS-014-TC04; parameterize every condition in this clause |
| AOS-014-AC03 | A child attempt event from stale epoch cannot mutate current task; exported traces honor Restricted local-only policy. | AOS-014-S1, AOS-014-S2, AOS-014-S3; owning files/interfaces above | AOS-014-TC01, AOS-014-TC02, AOS-014-TC03, AOS-014-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-014-S1](cursor/prompts/AOS-014-S1.md) | AOS-003, AOS-012 | Propagate goal/task/attempt/epoch/trace IDs and redacted local spans through transactions/adapters/verifiers. | AOS-014-TC01; command/report/exit, immutable evidence and diff |
| [AOS-014-S2](cursor/prompts/AOS-014-S2.md) | AOS-014-S1 | Post-commit event notification with DB-backed paginated SSE replay, expiry checks, bounded buffers and decimal cursors. | AOS-014-TC02; command/report/exit, immutable evidence and diff |
| [AOS-014-S3](cursor/prompts/AOS-014-S3.md) | AOS-014-S2 | Disconnect/duplicate/retention/>2^53/redaction fixtures and exporter-outage correctness proof. | AOS-014-TC01, AOS-014-TC02, AOS-014-TC03, AOS-014-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-014-TC01 | integration | `tests/integration/test_aos_014.py::test_cursor_commit_and_restart` | Later writer waits for earlier commit; rollback gap allowed; restarted stream returns all scoped task+goal events. |
| AOS-014-TC02 | e2e | `tests/integration/test_aos_014.py::test_sse_reconnect_decimal_cursor` | Disconnect after N, reconnect and dedupe; cursor >2^53 remains exact in browser; expired retention needs authoritative snapshot. |
| AOS-014-TC03 | security | `tests/integration/test_aos_014.py::test_redacted_scoped_events` | Foreign/stale events cannot change current task; synthetic secret never in JSON/spans/export logs. |
| AOS-014-TC04 | chaos | `tests/integration/test_aos_014.py::test_notification_exporter_loss` | Fanout or Phoenix down loses no canonical event/task truth; replay catches missing notifications. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_014.py --junitxml=evidence/AOS-014.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.


---

<!-- Source: plans/AOS-015-implementation-plan.md -->

# AOS-015 — Hardware probe integration and versioned capability manifest: implementation plan

**Release:** R1. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-001. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](testing/TEST_EXECUTION.md) and [source spec](specification/specs/AOS-015.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

AgentOS accurately measures installed CPU/GPU/RAM/disk/power and chooses feasible local model candidates without treating simulated specs as real.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/resources/probe.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/resources/catalog.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/resources/benchmark.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/cli/hardware.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `HardwareProbe.collect(read_only=True) -> HardwareManifest`
- `ModelCatalog.candidates(profile, required_capability) -> CandidateModels`
- `PlacementPlanner.propose(manifest, limits) -> PlacementProposal`

**Migration ownership:** Versioned hardware/model manifests and protected hashes; no upload of device identifiers by default.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-015-F01 | Inventory existing `hardware-probe` skill and `hwprobe.py` source/tests; verify claimed five simulated profiles, provenance and license. Run read-only OS probes (`nvidia-smi`, CPU info, RAM, upower, ROCm/macOS when available); missing tool reported unsupported, not 0 resources. | AOS-015-S1, AOS-015-S2, AOS-015-S3; owning files/interfaces above | AOS-015-TC01, AOS-015-TC02, AOS-015-TC03, AOS-015-TC04; parameterize every condition in this clause |
| AOS-015-F02 | Define signed/versioned `HardwareManifest` with OS/kernel, accelerator type, total/free VRAM, RAM, driver/runtime, measured/estimated bandwidth, thermal/battery/AC status, time and permissions; avoid privileged probing. | AOS-015-S1, AOS-015-S2, AOS-015-S3; owning files/interfaces above | AOS-015-TC01, AOS-015-TC02, AOS-015-TC03, AOS-015-TC04; parameterize every condition in this clause |
| AOS-015-F03 | A model-role catalog estimates resident memory as weights + KV + overhead, capability and license; no guaranteed tok/s from bandwidth estimate. Select steward by safe fit then benchmark actual TTFT/throughput. | AOS-015-S1, AOS-015-S2, AOS-015-S3; owning files/interfaces above | AOS-015-TC01, AOS-015-TC02, AOS-015-TC03, AOS-015-TC04; parameterize every condition in this clause |
| AOS-015-F04 | Re-probe on install/boot/drivers/catalog changes and preserve previous manifest for before/after comparison; allow user pin with an explicit degraded warning. | AOS-015-S1, AOS-015-S2, AOS-015-S3; owning files/interfaces above | AOS-015-TC01, AOS-015-TC02, AOS-015-TC03, AOS-015-TC04; parameterize every condition in this clause |
| AOS-015-AC01 | Run probe on actual Omen: record GPU name and real VRAM, RAM, driver and power; missing nvidia-smi gives explicit fallback. | AOS-015-S1, AOS-015-S2, AOS-015-S3; owning files/interfaces above | AOS-015-TC01, AOS-015-TC02, AOS-015-TC03, AOS-015-TC04; parameterize every condition in this clause |
| AOS-015-AC02 | Five attached simulated profile fixtures (smoke-checked in this revision) pass expected placement/low-memory degradation; no silent cloud selection for Restricted work. | AOS-015-S1, AOS-015-S2, AOS-015-S3; owning files/interfaces above | AOS-015-TC01, AOS-015-TC02, AOS-015-TC03, AOS-015-TC04; parameterize every condition in this clause |
| AOS-015-AC03 | Non-privileged probe doesn't change NVIDIA driver/prime config; manifests parse from fresh JSON Schema. | AOS-015-S1, AOS-015-S2, AOS-015-S3; owning files/interfaces above | AOS-015-TC01, AOS-015-TC02, AOS-015-TC03, AOS-015-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-015-S1](cursor/prompts/AOS-015-S1.md) | AOS-001 | Inventory original hwprobe source/license/presets and adapt typed uncertainty/probe-method manifest without installing drivers. | AOS-015-TC01; command/report/exit, immutable evidence and diff |
| [AOS-015-S2](cursor/prompts/AOS-015-S2.md) | AOS-015-S1 | Read-only physical probes and candidate memory estimates distinguish unsupported/missing from zero capacity. | AOS-015-TC02; command/report/exit, immutable evidence and diff |
| [AOS-015-S3](cursor/prompts/AOS-015-S3.md) | AOS-015-S2 | Preset/low-memory fixtures plus explicit real-machine manifest and measured placement proposal. | AOS-015-TC01, AOS-015-TC02, AOS-015-TC03, AOS-015-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-015-TC01 | unit | `tests/integration/test_aos_015.py::test_five_presets_and_missing_tools` | All five attached preset fixtures parse as simulated; missing nvidia-smi unsupported, not zero VRAM or made-up GPU. |
| AOS-015-TC02 | contract | `tests/integration/test_aos_015.py::test_model_fit_uncertainty` | Weight/KV/overhead budget enforced, bandwidth estimate not labelled measured throughput; license/capability refs required. |
| AOS-015-TC03 | live | `tests/integration/test_aos_015.py::test_real_hardware_read_only` | Actual GPU/VRAM/RAM/driver/power observed without driver/prime mutation; no network upload or privileged probing. |
| AOS-015-TC04 | integration | `tests/integration/test_aos_015.py::test_manifest_version_change` | Probe/catalog/version change creates new hashed manifest with old evidence retained and explicit user pin/degraded result. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_015.py --junitxml=evidence/AOS-015.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.


---

<!-- Source: plans/AOS-016-implementation-plan.md -->

# AOS-016 — Local inference adapter and warm/cold/pressure benchmarking: implementation plan

**Release:** R1. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-011, AOS-015. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](testing/TEST_EXECUTION.md) and [source spec](specification/specs/AOS-016.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

A user can invoke an offline steward locally, measure response speed and memory use on the actual GPU, and fail conservatively when inference is unavailable.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/brokers/inference/base.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/brokers/inference/ollama.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/brokers/inference/api.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/brokers/inference/model_manager.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/resources/benchmark.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `InferenceProvider.generate/stream/capabilities(request)`
- `ModelManager.admit_load/model_status/unload(model_ref)`
- `BenchmarkRunner.measure(profile, model_digest, corpus) -> BenchmarkReport`

**Migration ownership:** Model/runtime/benchmark metadata and inference usage/route refs; raw API secrets outside tables/worker scope.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-016-F01 | Implement `InferenceProvider` contract for chat/generate/stream/embed with capability manifest, model version, context/token budget, retries and actual/unknown resource usage; first implementation Ollama with local endpoint. | AOS-016-S1, AOS-016-S2, AOS-016-S3; owning files/interfaces above | AOS-016-TC01, AOS-016-TC02, AOS-016-TC03, AOS-016-TC04; parameterize every condition in this clause |
| AOS-016-F02 | Choose a small legal-to-distribute instruct model from measured hardware catalog; run bounded prompt, disable cloud fallback when offline/Restricted. Warm and cold start benchmark; TTFT, tokens/s, completion and GPU/CPU RSS measured. | AOS-016-S1, AOS-016-S2, AOS-016-S3; owning files/interfaces above | AOS-016-TC01, AOS-016-TC02, AOS-016-TC03, AOS-016-TC04; parameterize every condition in this clause |
| AOS-016-F03 | Overload guard: queue/cancel at capacity, avoid multiple resident copies, CPU deterministic fallback for status/routing, communicate unavailable instead of silently calling API. | AOS-016-S1, AOS-016-S2, AOS-016-S3; owning files/interfaces above | AOS-016-TC01, AOS-016-TC02, AOS-016-TC03, AOS-016-TC04; parameterize every condition in this clause |
| AOS-016-F04 | Tie inference events to task/trace and preserve memory-source citations if used by Ask. | AOS-016-S1, AOS-016-S2, AOS-016-S3; owning files/interfaces above | AOS-016-TC01, AOS-016-TC02, AOS-016-TC03, AOS-016-TC04; parameterize every condition in this clause |
| AOS-016-AC01 | Full network disabled: steward answers bounded local prompts and emits no external requests. | AOS-016-S1, AOS-016-S2, AOS-016-S3; owning files/interfaces above | AOS-016-TC01, AOS-016-TC02, AOS-016-TC03, AOS-016-TC04; parameterize every condition in this clause |
| AOS-016-AC02 | Warm and cold runs reported separately on physical Omen, with model size and actual VRAM; memory overload refuses safely and recovers. | AOS-016-S1, AOS-016-S2, AOS-016-S3; owning files/interfaces above | AOS-016-TC01, AOS-016-TC02, AOS-016-TC03, AOS-016-TC04; parameterize every condition in this clause |
| AOS-016-AC03 | Timeout and model unload mid-stream lead to explicit degraded/unavailable status, not half a success event. | AOS-016-S1, AOS-016-S2, AOS-016-S3; owning files/interfaces above | AOS-016-TC01, AOS-016-TC02, AOS-016-TC03, AOS-016-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-016-S1](cursor/prompts/AOS-016-S1.md) | AOS-011, AOS-015 | Typed provider protocol, Ollama adapter and fake transport fixtures with deadlines/deltas/unknown usage. | AOS-016-TC01; command/report/exit, immutable evidence and diff |
| [AOS-016-S2](cursor/prompts/AOS-016-S2.md) | AOS-016-S1 | Measured model admission/warm-cold/load/unload/pressure path and local-only policy; no silent cloud fallback. | AOS-016-TC02; command/report/exit, immutable evidence and diff |
| [AOS-016-S3](cursor/prompts/AOS-016-S3.md) | AOS-016-S2 | Baseline opt-in one API SDK adapter contract (MVP-X01), credential-handle separation and independently scoped live compatibility plus physical local benchmark. | AOS-016-TC01, AOS-016-TC02, AOS-016-TC03, AOS-016-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-016-TC01 | contract | `tests/integration/test_aos_016.py::test_inference_stream_failures` | Deltas/terminal/errors/unknown usage typed; partial failure not reported successful; context/token/deadline bounds enforced. |
| AOS-016-TC02 | security | `tests/integration/test_aos_016.py::test_restricted_route_no_fallback` | Restricted/offline requests cannot select API even if local model missing/OOM; denied destination cannot be activated by prompt. |
| AOS-016-TC03 | live | `tests/integration/test_aos_016.py::test_local_warm_cold_benchmark` | Actual installed model/hash/hardware produces separate warm/cold TTFT/quality/RSS/VRAM measurements; no simulated performance pass. |
| AOS-016-TC04 | live | `tests/integration/test_aos_016.py::test_approved_sdk_adapter` | Explicit eligible API route with consent/cap and protected credential handle works; mocked CI alone cannot establish live account/version compatibility. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_016.py --junitxml=evidence/AOS-016.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.


---

<!-- Source: plans/AOS-017-implementation-plan.md -->

# AOS-017 — Offline Ask and source-scoped memory interaction: implementation plan

**Release:** R1. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-011, AOS-016. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](testing/TEST_EXECUTION.md) and [source spec](specification/specs/AOS-017.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

A user can quickly ask the primary local AI offline and retrieve previously approved project memory without leaking information across scopes.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/api/routes/ask.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/cli/ask.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/memory/context.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/memory/search.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/ask.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `AskService.respond(actor, request) -> AsyncIterator[AskEvent]`
- `ContextCompiler.compose(actor, contract, memories, token_budget) -> ContextPack`
- `AskResult.provenance() -> SourceLinks`

**Migration ownership:** Scoped Ask request/idempotency/context/provenance refs; raw text retention opt-in.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-017-F01 | Build CLI `agentos ask` and thin HTTP API; classify request, select local model, retrieve memory using owner/project filters and compile small context pack with source refs and untrusted-content wrapping. | AOS-017-S1, AOS-017-S2, AOS-017-S3; owning files/interfaces above | AOS-017-TC01, AOS-017-TC02, AOS-017-TC03, AOS-017-TC04; parameterize every condition in this clause |
| AOS-017-F02 | No internet or subscription required to boot or answer; user sees cold-start/unavailable errors and provenance when memory used. Provide optional lightweight web Ask input if interface scaffold exists; not a frontend gate. | AOS-017-S1, AOS-017-S2, AOS-017-S3; owning files/interfaces above | AOS-017-TC01, AOS-017-TC02, AOS-017-TC03, AOS-017-TC04; parameterize every condition in this clause |
| AOS-017-F03 | Use deterministic intent bounds and timeouts; avoid prompt-only privacy decisions. Store only consented content, with corrections captured separately from responses. | AOS-017-S1, AOS-017-S2, AOS-017-S3; owning files/interfaces above | AOS-017-TC01, AOS-017-TC02, AOS-017-TC03, AOS-017-TC04; parameterize every condition in this clause |
| AOS-017-AC01 | A-1: 10 fixed queries offline including 3 project-memory recalls and malicious 'enable cloud' prompt; no observed/accessible outbound inference. | AOS-017-S1, AOS-017-S2, AOS-017-S3; owning files/interfaces above | AOS-017-TC01, AOS-017-TC02, AOS-017-TC03, AOS-017-TC04; parameterize every condition in this clause |
| AOS-017-AC02 | Latency distribution measured on actual hardware; provisional warm p95 TTFT ≤3 s only if hardware ADR confirms feasibility. | AOS-017-S1, AOS-017-S2, AOS-017-S3; owning files/interfaces above | AOS-017-TC01, AOS-017-TC02, AOS-017-TC03, AOS-017-TC04; parameterize every condition in this clause |
| AOS-017-AC03 | Different project memory never retrieved; missing local model returns actionable error, not unauthorized cloud response. | AOS-017-S1, AOS-017-S2, AOS-017-S3; owning files/interfaces above | AOS-017-TC01, AOS-017-TC02, AOS-017-TC03, AOS-017-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-017-S1](cursor/prompts/AOS-017-S1.md) | AOS-011, AOS-016 | Local-only Ask handler/CLI with project/label bounds, FTS recall and context source hashes. | AOS-017-TC01; command/report/exit, immutable evidence and diff |
| [AOS-017-S2](cursor/prompts/AOS-017-S2.md) | AOS-017-S1 | Streaming terminal status/timeout/degraded UI and separate explicit correction/memory write path. | AOS-017-TC02; command/report/exit, immutable evidence and diff |
| [AOS-017-S3](cursor/prompts/AOS-017-S3.md) | AOS-017-S2 | A-1 ten-prompt source/scope/no-cloud fixtures and actual network-disabled quality/latency measurements. | AOS-017-TC01, AOS-017-TC02, AOS-017-TC03, AOS-017-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-017-TC01 | integration | `tests/integration/test_aos_017.py::test_ten_prompt_ask_fixture` | Ten fixed queries include three source-linked recalls and hostile enable-cloud; correct scope/provenance and terminal status. |
| AOS-017-TC02 | security | `tests/integration/test_aos_017.py::test_memory_and_prompt_scope` | Another project's memory and untrusted enable-route instructions cannot enter pack or change local-only policy. |
| AOS-017-TC03 | chaos | `tests/integration/test_aos_017.py::test_missing_model_midstream` | Missing/unloaded model or interrupted stream returns safe degraded/error without fabricated answer or completion. |
| AOS-017-TC04 | live | `tests/integration/test_aos_017.py::test_a1_network_disabled` | Actual local Ask works with public egress disabled; warm latency target locked by hardware ADR, not silently waived. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_017.py --junitxml=evidence/AOS-017.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.


---

<!-- Source: plans/AOS-018-implementation-plan.md -->

# AOS-018 — Offline, degraded-mode and foreground-resource safety tests: implementation plan

**Release:** R1. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-015, AOS-016, AOS-017. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](testing/TEST_EXECUTION.md) and [source spec](specification/specs/AOS-018.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

Offline Ask remains useful without cloud/network, while CPU/GPU pressure does not cause resource starvation or corrupt task state.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/resources/admission.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/resources/probe.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/execution/task_workflow.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/cli/doctor.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `RuntimeGovernor.observe/admit/degrade(snapshot, job) -> Admission`
- `DegradedStatus.reason -> TypedReason`
- `OfflineGateRunner.run(profile, corpus) -> GateEvidence`

**Migration ownership:** Resource observation/admission/degraded reason events; only coarse MVP limits, no R4 optimizer.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-018-F01 | Build OS-level no-network test harness and optional network namespace; assert no DNS, HTTP or provider CLI fallback for local-only work. Test model cold load, unload and abort during response. | AOS-018-S1, AOS-018-S2, AOS-018-S3; owning files/interfaces above | AOS-018-TC01, AOS-018-TC02, AOS-018-TC03, AOS-018-TC04; parameterize every condition in this clause |
| AOS-018-F02 | Sample GPU VRAM/compute, CPU, RAM, battery/AC, thermal flags and active-foreground policy; implement conservative admission ceiling and a deterministic steward control fallback if GPU unavailable. | AOS-018-S1, AOS-018-S2, AOS-018-S3; owning files/interfaces above | AOS-018-TC01, AOS-018-TC02, AOS-018-TC03, AOS-018-TC04; parameterize every condition in this clause |
| AOS-018-F03 | Test prompt/time budget, OOM recovery, model process restart, disk pressure and cloud account absence. Distinguish intentional queue from hung service. | AOS-018-S1, AOS-018-S2, AOS-018-S3; owning files/interfaces above | AOS-018-TC01, AOS-018-TC02, AOS-018-TC03, AOS-018-TC04; parameterize every condition in this clause |
| AOS-018-AC01 | No egress in network-disabled A-1, including DNS and model auto-download. | AOS-018-S1, AOS-018-S2, AOS-018-S3; owning files/interfaces above | AOS-018-TC01, AOS-018-TC02, AOS-018-TC03, AOS-018-TC04; parameterize every condition in this clause |
| AOS-018-AC02 | Under synthetic GPU allocation pressure, heavy inference waits/steps down and existing durable tasks remain recoverable. | AOS-018-S1, AOS-018-S2, AOS-018-S3; owning files/interfaces above | AOS-018-TC01, AOS-018-TC02, AOS-018-TC03, AOS-018-TC04; parameterize every condition in this clause |
| AOS-018-AC03 | Battery mode and disabled GPU produce explicit CPU or unavailable states without silent cloud fallbacks. | AOS-018-S1, AOS-018-S2, AOS-018-S3; owning files/interfaces above | AOS-018-TC01, AOS-018-TC02, AOS-018-TC03, AOS-018-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-018-S1](cursor/prompts/AOS-018-S1.md) | AOS-015, AOS-016, AOS-017 | Explicit conservative process/CPU/RAM/VRAM/disk caps and observed/battery/degraded states. | AOS-018-TC01; command/report/exit, immutable evidence and diff |
| [AOS-018-S2](cursor/prompts/AOS-018-S2.md) | AOS-018-S1 | No-network harness, model restart/OOM/unload and foreground-priority fixtures with clear queue-vs-hang diagnostics. | AOS-018-TC02; command/report/exit, immutable evidence and diff |
| [AOS-018-S3](cursor/prompts/AOS-018-S3.md) | AOS-018-S2 | Actual physical resource/offline/cancellation recovery run and observed incident/latency evidence. | AOS-018-TC01, AOS-018-TC02, AOS-018-TC03, AOS-018-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-018-TC01 | security | `tests/integration/test_aos_018.py::test_offline_dns_no_provider` | OS-network-disabled Ask performs no DNS/provider fallback; absent account has no effect on local path. |
| AOS-018-TC02 | chaos | `tests/integration/test_aos_018.py::test_oom_disk_model_restart` | Inject pressure/disk full/model kill; stop admissions, preserve events/evidence, bounded recover/degrade. |
| AOS-018-TC03 | integration | `tests/integration/test_aos_018.py::test_capacity_queue_and_cancel` | Known ceiling queues excess work; cancellation ends no-new-admissions immediately and reports in-flight effects honestly. |
| AOS-018-TC04 | live | `tests/integration/test_aos_018.py::test_foreground_pressure_profile` | Actual hardware under approved pressure stays within recorded profile limits; no false guarantee of fine-grained consumer GPU partitioning. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_018.py --junitxml=evidence/AOS-018.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.


---

<!-- Source: plans/AOS-013-implementation-plan.md -->

# AOS-013 — Research source snapshots, hashes, passage spans and claim evidence: implementation plan

**Release:** R2. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-002, AOS-008. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](testing/TEST_EXECUTION.md) and [source spec](specification/specs/AOS-013.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

A research claim is traceable to an actual retained and fetched source, with exact text offset and source content hash, not just a URL in generated prose.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/contracts/research.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/research/sources.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/research/extract.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/research/claims.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/repositories/research.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `SourceStore.commit_fetch(actor, receipt, raw_blob, text_blob) -> SnapshotRef`
- `PassageResolver.resolve(snapshot_ref, start_offset, end_offset) -> VerifiedPassage`
- `ClaimStore.attach_evidence(actor, claim_ref, passages) -> ClaimEvidence`

**Migration ownership:** 0005_research: research_request/source_snapshot/claim/claim_passage/verification_report; raw/text hashes, extraction/offset versions and scope.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-013-F01 | Schema `research_source_snapshot` includes request URL, verified terminal URL, redirects, timestamp, status, type, byte limit, SHA-256 raw fetch hash, normalized text hash, extractor version, privacy class and encrypted/protected store key. | AOS-013-S1, AOS-013-S2, AOS-013-S3; owning files/interfaces above | AOS-013-TC01, AOS-013-TC02, AOS-013-TC03, AOS-013-TC04; parameterize every condition in this clause |
| AOS-013-F02 | Retain source text with stable UTF-8 offsets and extractor-specific mapping to original bytes where possible; passages referenced as `(source_id,start,end,normalization_version)`. | AOS-013-S1, AOS-013-S2, AOS-013-S3; owning files/interfaces above | AOS-013-TC01, AOS-013-TC02, AOS-013-TC03, AOS-013-TC04; parameterize every condition in this clause |
| AOS-013-F03 | `claim_evidence` stores claim text/hash, one-to-many source passage refs, quote-match status, support verdict, conflict set and source-fetch errors. | AOS-013-S1, AOS-013-S2, AOS-013-S3; owning files/interfaces above | AOS-013-TC01, AOS-013-TC02, AOS-013-TC03, AOS-013-TC04; parameterize every condition in this clause |
| AOS-013-F04 | Canonical source IDs only minted by trusted reader, not model text; static corpus fixtures for redirects, corrupted/truncated content, table extraction ambiguity. | AOS-013-S1, AOS-013-S2, AOS-013-S3; owning files/interfaces above | AOS-013-TC01, AOS-013-TC02, AOS-013-TC03, AOS-013-TC04; parameterize every condition in this clause |
| AOS-013-AC01 | Invalid source ID, missing passage, offset outside snapshot, changed source body, and fabricated URL all rejected. | AOS-013-S1, AOS-013-S2, AOS-013-S3; owning files/interfaces above | AOS-013-TC01, AOS-013-TC02, AOS-013-TC03, AOS-013-TC04; parameterize every condition in this clause |
| AOS-013-AC02 | Exact-quote fixture passes only when normalization recorded; page with truncated table marked insufficient, not invented. | AOS-013-S1, AOS-013-S2, AOS-013-S3; owning files/interfaces above | AOS-013-TC01, AOS-013-TC02, AOS-013-TC03, AOS-013-TC04; parameterize every condition in this clause |
| AOS-013-AC03 | Fetch records immutable; claim verdict references explicit extractor version and source hash. | AOS-013-S1, AOS-013-S2, AOS-013-S3; owning files/interfaces above | AOS-013-TC01, AOS-013-TC02, AOS-013-TC03, AOS-013-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-013-S1](cursor/prompts/AOS-013-S1.md) | AOS-002, AOS-008 | Immutable source/claim/Pydantic schema and Alembic metadata, protected raw/text artifact refs. | AOS-013-TC01; command/report/exit, immutable evidence and diff |
| [AOS-013-S2](cursor/prompts/AOS-013-S2.md) | AOS-013-S1 | Canonical NFC UTF-8 text and half-open byte passage offsets; explicit charset/truncation/version semantics. | AOS-013-TC02; command/report/exit, immutable evidence and diff |
| [AOS-013-S3](cursor/prompts/AOS-013-S3.md) | AOS-013-S2 | Hash/source/scope/offset fabrication fixtures and offline stored-evidence reconstruction. | AOS-013-TC01, AOS-013-TC02, AOS-013-TC03, AOS-013-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-013-TC01 | migration | `tests/integration/test_aos_013.py::test_research_scope_integrity` | Wrong project/goal/source/claim linkage fails; immutable fetch rows cannot silently overwrite extractor version. |
| AOS-013-TC02 | contract | `tests/integration/test_aos_013.py::test_utf8_offsets_hashes` | Non-ASCII passage offsets validate byte boundaries; out-of-range/split character/hash mismatch rejected. |
| AOS-013-TC03 | security | `tests/integration/test_aos_013.py::test_fabricated_source_reference` | Model-generated URL/ID without broker-retained successful fetch cannot pass evidence resolution. |
| AOS-013-TC04 | integration | `tests/integration/test_aos_013.py::test_snapshot_versions_truncation` | Changed body/re-extraction creates new snapshot; truncated content stays incomplete and never invents missing table text. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_013.py --junitxml=evidence/AOS-013.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.


---

<!-- Source: plans/AOS-019-implementation-plan.md -->

# AOS-019 — Search abstraction and SSRF-safe web retrieval broker: implementation plan

**Release:** R2. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-008, AOS-009, AOS-013. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](testing/TEST_EXECUTION.md) and [source spec](specification/specs/AOS-019.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

AgentOS can search approved public web sources and fetch URLs without resolving or redirecting into internal endpoints, exposing secrets, or mixing reader and actor privileges.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/brokers/search/base.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/brokers/search/searxng.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/brokers/search/configured_api.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/research/fetch.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/sandbox/network.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `SearchProvider.search(query, policy, limits) -> SearchResults`
- `FetchBroker.fetch(actor, url, constraints) -> FetchReceipt`
- `PinnedHTTPConnector.connect(approved_ip, original_host, tls_policy) -> Connection`

**Migration ownership:** Search/fetch/redirect/egress observations and consent/account refs; raw restricted query retention disabled.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-019-F01 | Define `SearchProvider.search(query, constraints)` for configured API and optional SearXNG. Search query is off-device disclosure (including SearXNG upstream engines), recorded with consent/provider/labels. No search from Restricted tasks unless explicitly local-only index. | AOS-019-S1, AOS-019-S2, AOS-019-S3; owning files/interfaces above | AOS-019-TC01, AOS-019-TC02, AOS-019-TC03, AOS-019-TC04; parameterize every condition in this clause |
| AOS-019-F02 | `FetchBroker.fetch(url)` validates scheme, port, hostname, resolved IP sets (IPv4/IPv6), redirects, proxy bypass, content type, max bytes/time/redirects and protocol downgrade; deny private/loopback/link-local/metadata/multicast and IPv4-mapped IPv6 as appropriate. Re-resolve/validate on every redirect and connect to pinned, checked address to resist DNS rebinding. | AOS-019-S1, AOS-019-S2, AOS-019-S3; owning files/interfaces above | AOS-019-TC01, AOS-019-TC02, AOS-019-TC03, AOS-019-TC04; parameterize every condition in this clause |
| AOS-019-F03 | Network isolation must enforce the decision below application-level URL parser; no ambient browser cookies, cloud auth headers or arbitrary URL schemes. | AOS-019-S1, AOS-019-S2, AOS-019-S3; owning files/interfaces above | AOS-019-TC01, AOS-019-TC02, AOS-019-TC03, AOS-019-TC04; parameterize every condition in this clause |
| AOS-019-F04 | Results are untrusted candidates; no page text can request a new tool privilege or broaden egress. | AOS-019-S1, AOS-019-S2, AOS-019-S3; owning files/interfaces above | AOS-019-TC01, AOS-019-TC02, AOS-019-TC03, AOS-019-TC04; parameterize every condition in this clause |
| AOS-019-AC01 | SSRF fixture: 127.0.0.1, RFC1918, 169.254.169.254, DNS rebinding, IPv6 loopback, redirect to internal IP, alternative encoding blocked in resolver and sandbox. | AOS-019-S1, AOS-019-S2, AOS-019-S3; owning files/interfaces above | AOS-019-TC01, AOS-019-TC02, AOS-019-TC03, AOS-019-TC04; parameterize every condition in this clause |
| AOS-019-AC02 | Invalid content-type/oversized response safely terminated; search API failure not silently retried to a different provider. | AOS-019-S1, AOS-019-S2, AOS-019-S3; owning files/interfaces above | AOS-019-TC01, AOS-019-TC02, AOS-019-TC03, AOS-019-TC04; parameterize every condition in this clause |
| AOS-019-AC03 | SearXNG JSON 403 when not configured becomes explicit setup error; tests prove query count recorded as outbound disclosure. | AOS-019-S1, AOS-019-S2, AOS-019-S3; owning files/interfaces above | AOS-019-TC01, AOS-019-TC02, AOS-019-TC03, AOS-019-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-019-S1](cursor/prompts/AOS-019-S1.md) | AOS-008, AOS-009, AOS-013 | Configured search adapter with quotas/query-disclosure ledger and explicit JSON/setup errors; no automatic provider choice. | AOS-019-TC01; command/report/exit, immutable evidence and diff |
| [AOS-019-S2](cursor/prompts/AOS-019-S2.md) | AOS-019-S1 | Trusted HTTPS/IP pin/redirect/TLS/byte/deadline broker plus OS gateway policy; no ambient cookie/proxy/auth leakage. | AOS-019-TC02; command/report/exit, immutable evidence and diff |
| [AOS-019-S3](cursor/prompts/AOS-019-S3.md) | AOS-019-S2 | Resolver/connector and actual network denial fixtures for private/mixed/encoded/DNS-rebind URLs; live search only separately scoped. | AOS-019-TC01, AOS-019-TC02, AOS-019-TC03, AOS-019-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-019-TC01 | security | `tests/integration/test_aos_019.py::test_ssrf_resolver_redirect_matrix` | IPv4/IPv6 loopback/private/metadata/encoded/mixed-address and redirect/rebind variants denied before unsafe connect. |
| AOS-019-TC02 | contract | `tests/integration/test_aos_019.py::test_pinned_tls_and_limits` | Connector uses checked IP with original SNI/Host/cert validation; scheme downgrade/bytes/decompression/deadlines fail safely. |
| AOS-019-TC03 | integration | `tests/integration/test_aos_019.py::test_search_disclosure_setup_errors` | Query is recorded as outbound even via local frontend; JSON 403/config error never silent fallback to a different paid provider. |
| AOS-019-TC04 | live | `tests/integration/test_aos_019.py::test_configured_search_gateway` | Owner-approved installed provider/gateway shows allowed public path and effective private/direct bypass denial; fake transport is not OS proof. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_019.py --junitxml=evidence/AOS-019.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.


---

<!-- Source: plans/AOS-020-implementation-plan.md -->

# AOS-020 — Quarantined web reader and immutable source provenance: implementation plan

**Release:** R2. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-013, AOS-019. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](testing/TEST_EXECUTION.md) and [source spec](specification/specs/AOS-020.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

Every Delegate result is grounded in immutable fetched source snapshots processed by a sandboxed reader that has no privileged outbound-action tools.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/research/reader.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/research/extract.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/sandbox/profiles.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/sandbox/artifact_ingress.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `ReaderWorker.extract(snapshot_input, limits) -> ExtractedTextCandidate`
- `ExtractorRegistry.select(mime, version) -> Extractor`
- `ReaderBroker.finalize(output, source_ref) -> SnapshotRef`

**Migration ownership:** Extractor/output provenance and immutable protected text artifacts in research schema.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-020-F01 | Implement read-only `ReaderWorker` process/container with only fetch API capability; convert approved HTML/plain-text documents to normalized text with source ID, canonical URL, content hash, extractor version and passage offsets. | AOS-020-S1, AOS-020-S2, AOS-020-S3; owning files/interfaces above | AOS-020-TC01, AOS-020-TC02, AOS-020-TC03, AOS-020-TC04; parameterize every condition in this clause |
| AOS-020-F02 | Segregate reader from synthesis worker, which gets structured text observations not executable page instructions; reader has no private mounts, Git repo, secrets, agent provider auth or general tool dispatch. | AOS-020-S1, AOS-020-S2, AOS-020-S3; owning files/interfaces above | AOS-020-TC01, AOS-020-TC02, AOS-020-TC03, AOS-020-TC04; parameterize every condition in this clause |
| AOS-020-F03 | Reject truncated/malformed extract rather than claim complete source; record content limitations for tables/PDF/scripted sites. Avoid open-ended crawling; bound max pages, bytes and depth. | AOS-020-S1, AOS-020-S2, AOS-020-S3; owning files/interfaces above | AOS-020-TC01, AOS-020-TC02, AOS-020-TC03, AOS-020-TC04; parameterize every condition in this clause |
| AOS-020-AC01 | Every displayed citation resolves to a retained source snapshot. Corrupt/changed source hash causes refusal. | AOS-020-S1, AOS-020-S2, AOS-020-S3; owning files/interfaces above | AOS-020-TC01, AOS-020-TC02, AOS-020-TC03, AOS-020-TC04; parameterize every condition in this clause |
| AOS-020-AC02 | Malicious webpage asks for shell command/exfil: no actor gets request and no privileged tool invoked. | AOS-020-S1, AOS-020-S2, AOS-020-S3; owning files/interfaces above | AOS-020-TC01, AOS-020-TC02, AOS-020-TC03, AOS-020-TC04; parameterize every condition in this clause |
| AOS-020-AC03 | Extraction truncation and nontext document yield explicit incomplete evidence; duplicate URL fetches create versioned snapshots. | AOS-020-S1, AOS-020-S2, AOS-020-S3; owning files/interfaces above | AOS-020-TC01, AOS-020-TC02, AOS-020-TC03, AOS-020-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-020-S1](cursor/prompts/AOS-020-S1.md) | AOS-013, AOS-019 | Read-only no-network reader process and bounded HTML/plain-text extractor; separate privileged fetch/synthesis principals. | AOS-020-TC01; command/report/exit, immutable evidence and diff |
| [AOS-020-S2](cursor/prompts/AOS-020-S2.md) | AOS-020-S1 | Sanitized immutable text/provenance output through ingress, no arbitrary file writes/JS/actor tools. | AOS-020-TC02; command/report/exit, immutable evidence and diff |
| [AOS-020-S3](cursor/prompts/AOS-020-S3.md) | AOS-020-S2 | Injection/parser/bomb/duplicate/truncation fixtures and offline replay with exact source-hash trace. | AOS-020-TC01, AOS-020-TC02, AOS-020-TC03, AOS-020-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-020-TC01 | security | `tests/integration/test_aos_020.py::test_reader_injection_no_actor` | Page tells reader to read secret/send/shell; tools and OS deny, no actor privilege handed to synthesizer. |
| AOS-020-TC02 | contract | `tests/integration/test_aos_020.py::test_mime_html_sanitization` | HTML/text extract only, no active JS/HTML; unsupported PDF/table/truncation explicit incomplete. |
| AOS-020-TC03 | chaos | `tests/integration/test_aos_020.py::test_reader_limits_bomb` | Oversized/decompression/parser CPU/hang bounded and reader stopped; protected store rejects partial output. |
| AOS-020-TC04 | integration | `tests/integration/test_aos_020.py::test_reader_snapshot_replay` | Displayed source resolves exact retained body/version; duplicate URL fetch versions preserved, changed hash denied. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_020.py --junitxml=evidence/AOS-020.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.


---

<!-- Source: plans/AOS-021-implementation-plan.md -->

# AOS-021 — Deterministic source citation and exact quotation verifier: implementation plan

**Release:** R2. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-020. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](testing/TEST_EXECUTION.md) and [source spec](specification/specs/AOS-021.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

A research brief cannot mark a factual claim evidenced unless every cited source actually exists and quoted passages exactly match the retained source text under documented normalization.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/verification/citations.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/research/claims.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/cli/evidence.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `CitationVerifier.validate_refs(actor, claim, source_manifest) -> CitationResult`
- `QuoteVerifier.match(snapshot, byte_range, quote, normalization_version) -> QuoteResult`
- `EvidenceVerifier.verify_report(report_ref) -> DeterministicEvidenceReport`

**Migration ownership:** Quotation normalization/offset/hash/version/verdict metadata; never overwrite legacy evidence silently.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-021-F01 | Integrate candidate `verified-research-brief` skill after inspection. Parse brief into structured claims, citations, quotations and passage offsets; reject source IDs not minted from retained fetches. | AOS-021-S1, AOS-021-S2, AOS-021-S3; owning files/interfaces above | AOS-021-TC01, AOS-021-TC02, AOS-021-TC03, AOS-021-TC04; parameterize every condition in this clause |
| AOS-021-F02 | Exact quote normalization policy must specify Unicode NFKC or NFC choice, whitespace collapsing, HTML entity handling, punctuation and case behavior; retain both original and normalized snippets, and never normalize away substantive edits. | AOS-021-S1, AOS-021-S2, AOS-021-S3; owning files/interfaces above | AOS-021-TC01, AOS-021-TC02, AOS-021-TC03, AOS-021-TC04; parameterize every condition in this clause |
| AOS-021-F03 | Each claim uses real `source_id`, `start/end` and extractor version; offsets checked against source SHA. `SUPPORTED` requires subsequent AOS-022 semantic check; citation check alone yields `EVIDENCE_PRESENT`, not factual support. | AOS-021-S1, AOS-021-S2, AOS-021-S3; owning files/interfaces above | AOS-021-TC01, AOS-021-TC02, AOS-021-TC03, AOS-021-TC04; parameterize every condition in this clause |
| AOS-021-F04 | Deterministic verifier must operate without remote model and be rerunnable against immutable fixtures. | AOS-021-S1, AOS-021-S2, AOS-021-S3; owning files/interfaces above | AOS-021-TC01, AOS-021-TC02, AOS-021-TC03, AOS-021-TC04; parameterize every condition in this clause |
| AOS-021-AC01 | Pass exact quote with expected Unicode/whitespace normalization; reject fabricated quotation, out-of-range passage, URL-only citation and hash mismatch. | AOS-021-S1, AOS-021-S2, AOS-021-S3; owning files/interfaces above | AOS-021-TC01, AOS-021-TC02, AOS-021-TC03, AOS-021-TC04; parameterize every condition in this clause |
| AOS-021-AC02 | Claim with real source but unrelated passage passes source/quote check only and remains awaiting support review. | AOS-021-S1, AOS-021-S2, AOS-021-S3; owning files/interfaces above | AOS-021-TC01, AOS-021-TC02, AOS-021-TC03, AOS-021-TC04; parameterize every condition in this clause |
| AOS-021-AC03 | Fixtures are deterministic across process restarts; re-extraction with new version records new mapping not silent overwrite. | AOS-021-S1, AOS-021-S2, AOS-021-S3; owning files/interfaces above | AOS-021-TC01, AOS-021-TC02, AOS-021-TC03, AOS-021-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-021-S1](cursor/prompts/AOS-021-S1.md) | AOS-020 | Port inspected citation skill to canonical source hashes/byte offsets and typed claim manifests; reject legacy unsafe source IDs. | AOS-021-TC01; command/report/exit, immutable evidence and diff |
| [AOS-021-S2](cursor/prompts/AOS-021-S2.md) | AOS-021-S1 | Case-sensitive NFC/whitespace quote matcher with source/text boundary verification and explicit diagnostics. | AOS-021-TC02; command/report/exit, immutable evidence and diff |
| [AOS-021-S3](cursor/prompts/AOS-021-S3.md) | AOS-021-S2 | Offline rerunnable positive/fabrication/Unicode/laundering fixtures and CLI evidence report separate from support. | AOS-021-TC01, AOS-021-TC02, AOS-021-TC03, AOS-021-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-021-TC01 | contract | `tests/integration/test_aos_021.py::test_exact_quote_normalization` | Exact NFC/whitespace variants match; changed case/numbers/punctuation/substantive quote edit does not normalize away. |
| AOS-021-TC02 | security | `tests/integration/test_aos_021.py::test_fabricated_quote_url_offsets` | URL-only/fabricated source/out-of-range/split UTF-8/hash mismatch fail before semantic judging. |
| AOS-021-TC03 | integration | `tests/integration/test_aos_021.py::test_citation_not_support` | Real unrelated passage can show EVIDENCE_PRESENT but not SUPPORTED; no automatic factual pass. |
| AOS-021-TC04 | integration | `tests/integration/test_aos_021.py::test_offline_reproducibility` | Same immutable fixtures yield same results after restart; new extractor version needs new mapping. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_021.py --junitxml=evidence/AOS-021.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.


---

<!-- Source: plans/AOS-022-implementation-plan.md -->

# AOS-022 — Claim-support adjudication, contradiction and uncertainty labeling: implementation plan

**Release:** R2. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-021, AOS-016. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](testing/TEST_EXECUTION.md) and [source spec](specification/specs/AOS-022.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

A separately validated verifier distinguishes source presence from actual evidential support, flags conflicts, and refuses false certainty.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/verification/support.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/research/claims.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/brokers/inference/base.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `ClaimSupportVerifier.check(claim, passages, model_ref, rubric_ref) -> SupportVerdict`
- `SupportCalibrator.evaluate(labeled_corpus, verifier) -> CalibrationReport`
- `ResearchReport.label_claims(verdicts) -> ReviewedClaimViews`

**Migration ownership:** Support/rubric/model/prompt/corpus versions, uncertainty/rationale/correction refs; no fabricated calibrated confidence.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-022-F01 | Create a labeled fixture set with supported, unsupported, partially supported, conflicting and opinion/interpretation claims; calibrate adjudicator rubric with actual human labels. | AOS-022-S1, AOS-022-S2, AOS-022-S3; owning files/interfaces above | AOS-022-TC01, AOS-022-TC02, AOS-022-TC03, AOS-022-TC04; parameterize every condition in this clause |
| AOS-022-F02 | Use deterministic checks first. For semantic entailment, choose an independent model family where policy/hardware allow; on local-only hardware use local verifier with explicitly lower confidence and `UNKNOWN` when insufficient. | AOS-022-S1, AOS-022-S2, AOS-022-S3; owning files/interfaces above | AOS-022-TC01, AOS-022-TC02, AOS-022-TC03, AOS-022-TC04; parameterize every condition in this clause |
| AOS-022-F03 | Allow abstention. Treat multiple sources that repeat the same unsupported assertion as correlated, not independent corroboration. Do not claim 100% factual correctness from a second LLM. | AOS-022-S1, AOS-022-S2, AOS-022-S3; owning files/interfaces above | AOS-022-TC01, AOS-022-TC02, AOS-022-TC03, AOS-022-TC04; parameterize every condition in this clause |
| AOS-022-F04 | User output surfaces per-claim support verdict, uncertainty, evidence passage, contradiction IDs and human corrections. | AOS-022-S1, AOS-022-S2, AOS-022-S3; owning files/interfaces above | AOS-022-TC01, AOS-022-TC02, AOS-022-TC03, AOS-022-TC04; parameterize every condition in this clause |
| AOS-022-AC01 | Labeled examples: fabricated claim with valid URL rejected; contradicted claim flagged; true excerpt receives supported; ambiguous interpretation marked not strictly factual. | AOS-022-S1, AOS-022-S2, AOS-022-S3; owning files/interfaces above | AOS-022-TC01, AOS-022-TC02, AOS-022-TC03, AOS-022-TC04; parameterize every condition in this clause |
| AOS-022-AC02 | Verifier offline/unavailable returns UNKNOWN and requires edit/abstain; no auto-promotion of unverified claim. | AOS-022-S1, AOS-022-S2, AOS-022-S3; owning files/interfaces above | AOS-022-TC01, AOS-022-TC02, AOS-022-TC03, AOS-022-TC04; parameterize every condition in this clause |
| AOS-022-AC03 | Source conflict preserved rather than majority vote over duplicates. | AOS-022-S1, AOS-022-S2, AOS-022-S3; owning files/interfaces above | AOS-022-TC01, AOS-022-TC02, AOS-022-TC03, AOS-022-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-022-S1](cursor/prompts/AOS-022-S1.md) | AOS-021, AOS-016 | Human-labeled supported/contradicted/insufficient/ambiguous/opinion corpus with explicit rubric and deterministic prerequisites. | AOS-022-TC01; command/report/exit, immutable evidence and diff |
| [AOS-022-S2](cursor/prompts/AOS-022-S2.md) | AOS-022-S1 | Separately configured support model/role with safe local scheduling or consented eligible route; abstention and duplicate-source correlation. | AOS-022-TC02; command/report/exit, immutable evidence and diff |
| [AOS-022-S3](cursor/prompts/AOS-022-S3.md) | AOS-022-S2 | Calibration/conflict/unavailable fixtures and owner-visible uncertainty review; preserve separation of model verdict and required human rubric-review. | AOS-022-TC01, AOS-022-TC02, AOS-022-TC03, AOS-022-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-022-TC01 | contract | `tests/integration/test_aos_022.py::test_labeled_support_matrix` | Versioned fixture labels include positive/contradiction/unsupported/ambiguous; factual support never inferred only from URL existence. |
| AOS-022-TC02 | security | `tests/integration/test_aos_022.py::test_judge_route_injection` | Evidence instructions cannot change judge tools/provider; restricted evidence cannot use prohibited second model/API. |
| AOS-022-TC03 | integration | `tests/integration/test_aos_022.py::test_conflict_and_unavailable` | Correlated duplicates not majority-voted; source conflict retained; unavailable/malformed judge result UNKNOWN/abstain. |
| AOS-022-TC04 | live | `tests/integration/test_aos_022.py::test_calibrated_support_behavior` | Actual eligible independent model/role evaluated against reviewed corpus; report confusion/abstention and sample size, no truth guarantee. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_022.py --junitxml=evidence/AOS-022.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.


---

<!-- Source: plans/AOS-023-implementation-plan.md -->

# AOS-023 — Bounded Delegate planner, research brief output and R2 gate: implementation plan

**Release:** R2. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-019, AOS-020, AOS-021, AOS-022. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](testing/TEST_EXECUTION.md) and [source spec](specification/specs/AOS-023.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

A user can delegate a specific public-web research brief, inspect evidence and limitations, and obtain deterministic security guarantees around source retrieval.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/research/delegate.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/api/routes/research.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/cli/delegate.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/research/claims.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `DelegateService.submit(actor, request, idempotency_key) -> ResearchReceipt`
- `ResearchPlanner.propose(question, limits) -> BoundedQueries`
- `ResearchOrchestrator.run(request_ref) -> EvidenceBrief`

**Migration ownership:** Research task/goal linkage and bounded request/result artifact refs with immutable evidence manifest.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-023-F01 | Ask/Delegate/Build API routes remain distinct; R2 Delegate accepts a bounded question, allowed search providers, per-task fetch/latency/budget constraints and permitted topic data classes. | AOS-023-S1, AOS-023-S2, AOS-023-S3; owning files/interfaces above | AOS-023-TC01, AOS-023-TC02, AOS-023-TC03, AOS-023-TC04; parameterize every condition in this clause |
| AOS-023-F02 | Planner breaks request into ≤N research subqueries, calls approved search provider, fetcher and isolated reader; synthesizer constructs structured claim and source list; all factual claims go through source/quote and semantic support pipeline. | AOS-023-S1, AOS-023-S2, AOS-023-S3; owning files/interfaces above | AOS-023-TC01, AOS-023-TC02, AOS-023-TC03, AOS-023-TC04; parameterize every condition in this clause |
| AOS-023-F03 | Result includes objective question summary, evidence-backed claims, links/source snapshot IDs, uncertainty/contradictions, retrieval errors and fact-check results. Explicitly reject authenticated/private browsing and executable site instructions. | AOS-023-S1, AOS-023-S2, AOS-023-S3; owning files/interfaces above | AOS-023-TC01, AOS-023-TC02, AOS-023-TC03, AOS-023-TC04; parameterize every condition in this clause |
| AOS-023-F04 | R2 security gates include SSRF, DNS rebinding, prompt-injection reader/actor split and provider search disclosure logging. | AOS-023-S1, AOS-023-S2, AOS-023-S3; owning files/interfaces above | AOS-023-TC01, AOS-023-TC02, AOS-023-TC03, AOS-023-TC04; parameterize every condition in this clause |
| AOS-023-AC01 | D-1: ≥5 fixture briefs including fabricated quote, fabricated URL, claim contradiction, injection and SSRF attempt. All negative fixtures explicitly fail/abstain. | AOS-023-S1, AOS-023-S2, AOS-023-S3; owning files/interfaces above | AOS-023-TC01, AOS-023-TC02, AOS-023-TC03, AOS-023-TC04; parameterize every condition in this clause |
| AOS-023-AC02 | One authorized live public-web brief completes and every displayed citation resolves to retained successfully fetched source. | AOS-023-S1, AOS-023-S2, AOS-023-S3; owning files/interfaces above | AOS-023-TC01, AOS-023-TC02, AOS-023-TC03, AOS-023-TC04; parameterize every condition in this clause |
| AOS-023-AC03 | Network-disabled Ask still operates unchanged; no delegated task can open user secrets or call shell actor. | AOS-023-S1, AOS-023-S2, AOS-023-S3; owning files/interfaces above | AOS-023-TC01, AOS-023-TC02, AOS-023-TC03, AOS-023-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-023-S1](cursor/prompts/AOS-023-S1.md) | AOS-019, AOS-020, AOS-021, AOS-022 | Distinct Delegate request/admission with configured provider/consent and strict subquery/source/byte/time/budget bounds. | AOS-023-TC01; command/report/exit, immutable evidence and diff |
| [AOS-023-S2](cursor/prompts/AOS-023-S2.md) | AOS-023-S1 | Fetch→read→claim→cite→support pipeline with complete errors/truncation/uncertainty and deterministic offline fixture mode. | AOS-023-TC02; command/report/exit, immutable evidence and diff |
| [AOS-023-S3](cursor/prompts/AOS-023-S3.md) | AOS-023-S2 | D-1 adversarial briefs and separately authorized live public brief; disable Delegate without changing offline Ask/Build. | AOS-023-TC01, AOS-023-TC02, AOS-023-TC03, AOS-023-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-023-TC01 | e2e | `tests/e2e/test_aos_023.py::test_d1_fixture_briefs` | Five briefs cover fake URL/quote, contradiction, injection and SSRF; negatives fail/abstain explicitly. |
| AOS-023-TC02 | security | `tests/e2e/test_aos_023.py::test_delegate_scope_and_budgets` | Private authenticated browsing/shell/secret access denied; subqueries/sources/deadlines/paid caps cannot grow from model text. |
| AOS-023-TC03 | integration | `tests/e2e/test_aos_023.py::test_ask_build_independence` | Delegate disabled/search down does not break Ask or Build and no silent provider fallback occurs. |
| AOS-023-TC04 | live | `tests/e2e/test_aos_023.py::test_live_public_evidenced_brief` | Authorized question completes with every citation retained/resolvable, query disclosure and support/error labels. |

After tests exist, baseline command is `uv run --frozen pytest tests/e2e/test_aos_023.py --junitxml=evidence/AOS-023.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.


---

<!-- Source: plans/AOS-024-implementation-plan.md -->

# AOS-024 — Codex supported CLI adapter and contract suite: implementation plan

**Release:** R3. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-004, AOS-008, AOS-010. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](testing/TEST_EXECUTION.md) and [source spec](specification/specs/AOS-024.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

A second approved vendor harness can perform bounded work under exactly the same AgentOS worker contract and sandbox permissions as the first.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/brokers/harness/codex.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/brokers/harness/event_parser.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/brokers/harness/process_runner.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/sandbox/native_tool_gateway.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `CodexAdapter.validate/start/events/observe/cancel/collect(job)`
- `CodexCompatibilityProbe.inspect(binary, profile, auth_handle) -> Manifest`

**Migration ownership:** Second adapter version/auth-mode/profile/consent metadata, normalized vendor receipt/thread refs; no consumer credential brokerage.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-024-F01 | Implement Codex CLI adapter using officially supported headless/JSON interface and signed-in user's own permitted account. Do not handle consumer credentials directly or pool accounts; background usage requires express consent if applicable. | AOS-024-S1, AOS-024-S2, AOS-024-S3; owning files/interfaces above | AOS-024-TC01, AOS-024-TC02, AOS-024-TC03, AOS-024-TC04; parameterize every condition in this clause |
| AOS-024-F02 | Pin binary/protocol version; validate auth status using supported commands, protect config state from repo files, constrain execution worktree and tool permissions; never inherit arbitrary unattended approvals. | AOS-024-S1, AOS-024-S2, AOS-024-S3; owning files/interfaces above | AOS-024-TC01, AOS-024-TC02, AOS-024-TC03, AOS-024-TC04; parameterize every condition in this clause |
| AOS-024-F03 | Map Codex events/errors/usage to common schema; differentiate auth-required, 429, failure, structured output parse failure, no native resume and uncertain process effects. | AOS-024-S1, AOS-024-S2, AOS-024-S3; owning files/interfaces above | AOS-024-TC01, AOS-024-TC02, AOS-024-TC03, AOS-024-TC04; parameterize every condition in this clause |
| AOS-024-F04 | Adapter testing uses recorded sanitized synthetic events plus live optional smoke tests only on a synthetic repo under user consent. | AOS-024-S1, AOS-024-S2, AOS-024-S3; owning files/interfaces above | AOS-024-TC01, AOS-024-TC02, AOS-024-TC03, AOS-024-TC04; parameterize every condition in this clause |
| AOS-024-AC01 | Synthetic Codex JSON fixture parses to normalized events; corrupted stream and unknown field fail safely. | AOS-024-S1, AOS-024-S2, AOS-024-S3; owning files/interfaces above | AOS-024-TC01, AOS-024-TC02, AOS-024-TC03, AOS-024-TC04; parameterize every condition in this clause |
| AOS-024-AC02 | Malicious repo config cannot widen worktree or command scope. Cancellation, timeout, unauthorized auth and 429 yield correct states. | AOS-024-S1, AOS-024-S2, AOS-024-S3; owning files/interfaces above | AOS-024-TC01, AOS-024-TC02, AOS-024-TC03, AOS-024-TC04; parameterize every condition in this clause |
| AOS-024-AC03 | Parallel adapter test verifies no Claude-specific fields leak into kernel API. | AOS-024-S1, AOS-024-S2, AOS-024-S3; owning files/interfaces above | AOS-024-TC01, AOS-024-TC02, AOS-024-TC03, AOS-024-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-024-S1](cursor/prompts/AOS-024-S1.md) | AOS-004, AOS-008, AOS-010 | Current supported exec/JSONL/login-status interface pinned and mapped with sanitized fixture protocol; no model/kernel field coupling. | AOS-024-TC01; command/report/exit, immutable evidence and diff |
| [AOS-024-S2](cursor/prompts/AOS-024-S2.md) | AOS-024-S1 | Scoped config/workspace/native+OS permissions and bounded process/credential-tool isolation; no untested resume or approval bypass. | AOS-024-TC02; command/report/exit, immutable evidence and diff |
| [AOS-024-S3](cursor/prompts/AOS-024-S3.md) | AOS-024-S2 | Hostile repo/cancel/auth/quota/truncation fixtures plus consented synthetic live adapter parity evidence. | AOS-024-TC01, AOS-024-TC02, AOS-024-TC03, AOS-024-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-024-TC01 | contract | `tests/integration/test_aos_024.py::test_codex_normalized_stream` | Success/error/auth/quota/item/turn events normalize; unknown/truncated state data refuses unsafe transition, no Claude-specific public fields. |
| AOS-024-TC02 | security | `tests/integration/test_aos_024.py::test_codex_repo_config_permissions` | Repo config/AGENTS/MCP cannot widen sandbox, read credentials or protected parent refs; native/outer limits measured. |
| AOS-024-TC03 | chaos | `tests/integration/test_aos_024.py::test_codex_cancel_start_loss` | Silent timeout/child process cancellation and lost start receipt accurately reconciled; no automatic native resume. |
| AOS-024-TC04 | live | `tests/integration/test_aos_024.py::test_codex_live_adapter_parity` | Exact owner-authenticated binary/profile runs synthetic task under same protocol; required features/auth mode tested, not inferred from docs. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_024.py --junitxml=evidence/AOS-024.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.


---

<!-- Source: plans/AOS-025-implementation-plan.md -->

# AOS-025 — Build task DAG and bounded LangGraph reasoning/replan: implementation plan

**Release:** R3. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-003, AOS-016. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](testing/TEST_EXECUTION.md) and [source spec](specification/specs/AOS-025.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

A user intent is converted into an executable acyclic work plan with dependencies, acceptance checks and conservative bounded replanning.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/contracts/plan.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/plans.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/execution/build_plan.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/memory/context.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `PlanProposalService.propose(actor, contract, inventory) -> PlanProposal`
- `PlanValidator.validate(proposal, contract, capability_manifest) -> ValidatedDAG`
- `Supervisor.replan(actor, failure_ref, expected_plan_version) -> PlanRevision`

**Migration ownership:** 0006_plans_fleet: plan_version/plan_task_link and task DAG metadata; parent hash/version and bounded revisions.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-025-F01 | Planner consumes immutable goal contract, project inventory and capabilities, produces typed DAG with task IDs, required worker/tools, expected artifact/check and dependency edges. Enforce bounded task count, depth and budget before admission. | AOS-025-S1, AOS-025-S2, AOS-025-S3; owning files/interfaces above | AOS-025-TC01, AOS-025-TC02, AOS-025-TC03, AOS-025-TC04; parameterize every condition in this clause |
| AOS-025-F02 | Use direct structured local/model call first, optionally a small LangGraph plan-review-revise subgraph where actual cycles justify it. LangGraph checkpoint never becomes authoritative task state. | AOS-025-S1, AOS-025-S2, AOS-025-S3; owning files/interfaces above | AOS-025-TC01, AOS-025-TC02, AOS-025-TC03, AOS-025-TC04; parameterize every condition in this clause |
| AOS-025-F03 | On verifier failure, propose a new plan version with reasoning and explicit approval if contract scope, privacy or cost changes. Long-running agents end milestones with a handoff and clean artifacts; prohibit recursive infinite replanning. | AOS-025-S1, AOS-025-S2, AOS-025-S3; owning files/interfaces above | AOS-025-TC01, AOS-025-TC02, AOS-025-TC03, AOS-025-TC04; parameterize every condition in this clause |
| AOS-025-AC01 | Planner output with cycles, missing acceptance checks or unapproved capability rejected. | AOS-025-S1, AOS-025-S2, AOS-025-S3; owning files/interfaces above | AOS-025-TC01, AOS-025-TC02, AOS-025-TC03, AOS-025-TC04; parameterize every condition in this clause |
| AOS-025-AC02 | Bounded replan terminates after configured attempts; changing contract scope needs new approved version. | AOS-025-S1, AOS-025-S2, AOS-025-S3; owning files/interfaces above | AOS-025-TC01, AOS-025-TC02, AOS-025-TC03, AOS-025-TC04; parameterize every condition in this clause |
| AOS-025-AC03 | A simple synthetic one-task plan works without LangGraph; graph mode yields equivalent task contract with traceable decisions. | AOS-025-S1, AOS-025-S2, AOS-025-S3; owning files/interfaces above | AOS-025-TC01, AOS-025-TC02, AOS-025-TC03, AOS-025-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-025-S1](cursor/prompts/AOS-025-S1.md) | AOS-003, AOS-016 | Typed bounded plan schema and deterministic DAG/capability/scope/budget validator with synthetic proposal fixtures. | AOS-025-TC01; command/report/exit, immutable evidence and diff |
| [AOS-025-S2](cursor/prompts/AOS-025-S2.md) | AOS-025-S1 | Direct structured local inference proposal and milestone handoff context; kernel commits approved plan/task refs only. | AOS-025-TC02; command/report/exit, immutable evidence and diff |
| [AOS-025-S3](cursor/prompts/AOS-025-S3.md) | AOS-025-S2 | Bounded repair/replan and optional small LangGraph interface parity; scope/cost/privacy changes require new contract consent. | AOS-025-TC01, AOS-025-TC02, AOS-025-TC03, AOS-025-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-025-TC01 | contract | `tests/integration/test_aos_025.py::test_dag_cycle_scope_budget` | Cycle/self-edge/missing check/unavailable worker/unapproved capability/too many nodes or aggregate overbudget rejected. |
| AOS-025-TC02 | integration | `tests/integration/test_aos_025.py::test_plan_version_and_handoff` | Validated plan versions persist immutable parent/hash; milestone output and fresh context preserve evidence and exact contract scope. |
| AOS-025-TC03 | security | `tests/integration/test_aos_025.py::test_replan_cannot_expand_authority` | Injected README/model proposal cannot widen privacy/paths/budget; contract change requires new version/consent. |
| AOS-025-TC04 | integration | `tests/integration/test_aos_025.py::test_bounded_replan_direct_graph` | Configured max replan terminates; direct one-task works without graph runtime; enabled graph yields same authoritative DAG contract. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_025.py --junitxml=evidence/AOS-025.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.


---

<!-- Source: plans/AOS-026-implementation-plan.md -->

# AOS-026 — Concurrent two-worker scheduler, worktree conflict control and admission: implementation plan

**Release:** R3. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-006, AOS-010, AOS-024, AOS-025. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](testing/TEST_EXECUTION.md) and [source spec](specification/specs/AOS-026.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

Two authorized workers execute independent plan steps concurrently without overwriting each other or exceeding CPU/GPU/provider/budget limits.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/kernel/scheduler.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/leases.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/budgets.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/resources/admission.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/execution/build_plan.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/verification/merge.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `Scheduler.claim_ready(actor, capacity) -> AttemptLease|Queued`
- `ResourceAdmission.reserve(uow, job, snapshot) -> Reservation`
- `BuildIntegrator.collect_fenced(attempts, base_sha) -> CandidateSet`

**Migration ownership:** Plan/fleet/reservation/candidate/common-ancestor metadata and ready-task indexes; scoped epoch and known cash constraints.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-026-F01 | Task DAG scheduler determines ready nodes, leases worker attempts with fencing epochs, admits only after effective trust/privacy/autonomy, quota, cost and resource constraints. | AOS-026-S1, AOS-026-S2, AOS-026-S3; owning files/interfaces above | AOS-026-TC01, AOS-026-TC02, AOS-026-TC03, AOS-026-TC04; parameterize every condition in this clause |
| AOS-026-F02 | Each worker receives isolated checked-out worktree branch; common ancestor tracked, diff hashes and merge-conflict checks done before integration. Limit WIP/concurrent harness processes; support queue priorities and urgent reserve without subscription quota abuse. | AOS-026-S1, AOS-026-S2, AOS-026-S3; owning files/interfaces above | AOS-026-TC01, AOS-026-TC02, AOS-026-TC03, AOS-026-TC04; parameterize every condition in this clause |
| AOS-026-F03 | On GPU/foreground pressure no new heavy workers admitted, current work deferred safely; mismatched provider plan entitlement never silently falls back to unapproved cloud. | AOS-026-S1, AOS-026-S2, AOS-026-S3; owning files/interfaces above | AOS-026-TC01, AOS-026-TC02, AOS-026-TC03, AOS-026-TC04; parameterize every condition in this clause |
| AOS-026-F04 | On a conflict, stop automatic merge and present verifier/owner with alternatives; do not allow agent A to overwrite B's artifacts. | AOS-026-S1, AOS-026-S2, AOS-026-S3; owning files/interfaces above | AOS-026-TC01, AOS-026-TC02, AOS-026-TC03, AOS-026-TC04; parameterize every condition in this clause |
| AOS-026-AC01 | Two workers modify disjoint files and pass tests; conflicting same-line edits stop before protected merge. | AOS-026-S1, AOS-026-S2, AOS-026-S3; owning files/interfaces above | AOS-026-TC01, AOS-026-TC02, AOS-026-TC03, AOS-026-TC04; parameterize every condition in this clause |
| AOS-026-AC02 | Concurrency cap enforced under 8 competing synthetic jobs; stale attempt cannot publish; failure of one does not falsely complete dependent tasks. | AOS-026-S1, AOS-026-S2, AOS-026-S3; owning files/interfaces above | AOS-026-TC01, AOS-026-TC02, AOS-026-TC03, AOS-026-TC04; parameterize every condition in this clause |
| AOS-026-AC03 | Quota unknown route receives conservative behavior and Restricted never cloud-falls-back. | AOS-026-S1, AOS-026-S2, AOS-026-S3; owning files/interfaces above | AOS-026-TC01, AOS-026-TC02, AOS-026-TC03, AOS-026-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-026-S1](cursor/prompts/AOS-026-S1.md) | AOS-006, AOS-010, AOS-024, AOS-025 | Ready-node dependency query with atomic claim/epoch/resource/cash reservation and bounded priority ordering. | AOS-026-TC01; command/report/exit, immutable evidence and diff |
| [AOS-026-S2](cursor/prompts/AOS-026-S2.md) | AOS-026-S1 | Two independent adapter/worktree orchestration with common-ancestor receipts; cancel/failure propagation and foreground no-new-admissions. | AOS-026-TC02; command/report/exit, immutable evidence and diff |
| [AOS-026-S3](cursor/prompts/AOS-026-S3.md) | AOS-026-S2 | Eight-job concurrency stress, stale writes/dependency failure/unknown quota/conflict fixtures and actual two-worker footprint. | AOS-026-TC01, AOS-026-TC02, AOS-026-TC03, AOS-026-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-026-TC01 | integration | `tests/integration/test_aos_026.py::test_two_disjoint_workers` | Two allowed workers on disjoint files get separate leased workspaces/receipts without overriding results. |
| AOS-026-TC02 | integration | `tests/integration/test_aos_026.py::test_eight_jobs_capacity_budget` | Eight competing tasks never exceed cap; concurrent known-cash reservation cannot overspend; failed dependency never dispatched. |
| AOS-026-TC03 | security | `tests/integration/test_aos_026.py::test_stale_conflicting_results` | Stale epoch/cross-project result rejected; same-line overlap is conflict, no overwrite or automatic protected merge. |
| AOS-026-TC04 | live | `tests/integration/test_aos_026.py::test_two_worker_resource_limits` | Two certified live adapters respect actual configured host/process/foreground limits; unknown quota produces conservative behavior. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_026.py --junitxml=evidence/AOS-026.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.


---

<!-- Source: plans/AOS-027b-implementation-plan.md -->

# AOS-027b — Integrated multi-worker verification and protected merge: implementation plan

**Release:** R3. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-027a, AOS-026. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](testing/TEST_EXECUTION.md) and [source spec](specification/specs/AOS-027b.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

Concurrent worker results are integrated, re-verified on the final tree and merged only with fresh exact approval.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/verification/merge.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/verification/runner.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/approvals.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/execution/build_plan.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `IntegratedVerifier.verify(base_ref, accepted_attempts, contract) -> FinalCandidateEvidence`
- `BuildIntegrator.integrate(candidate_set) -> Candidate|Conflict`
- `MergeApprovalService.request_final(actor, evidence) -> ApprovalPreview`

**Migration ownership:** Final integrated tree/attempt membership/check-set/base/effect binding; reuse 027a approval/effect schema.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-027b-F01 | Extend the AOS-027a service after AOS-026. Collect fenced worker results, detect conflicts, construct the integrated candidate tree and run the complete required check set on that tree; reuse the R1 approval and evidence contracts. | AOS-027b-S1, AOS-027b-S2, AOS-027b-S3; owning files/interfaces above | AOS-027b-TC01, AOS-027b-TC02, AOS-027b-TC03, AOS-027b-TC04; parameterize every condition in this clause |
| AOS-027b-F02 | Verifier must run against the **candidate final tree** (post-integration for multiworker), not only each worktree's isolated passing tests. Use pinned known test commands with timeout and output limit; file diff signed with commit/tree SHA. | AOS-027b-S1, AOS-027b-S2, AOS-027b-S3; owning files/interfaces above | AOS-027b-TC01, AOS-027b-TC02, AOS-027b-TC03, AOS-027b-TC04; parameterize every condition in this clause |
| AOS-027b-F03 | Protected merge requires approval digest binding exact candidate commit, destination branch, check set, project/action policy version and expiry. Revalidate immediately before side effect; unexpected external effect goes RECONCILING. | AOS-027b-S1, AOS-027b-S2, AOS-027b-S3; owning files/interfaces above | AOS-027b-TC01, AOS-027b-TC02, AOS-027b-TC03, AOS-027b-TC04; parameterize every condition in this clause |
| AOS-027b-F04 | Missing evidence, failed/UNKNOWN checks, modified diff after approval or policy mismatch means no merge. | AOS-027b-S1, AOS-027b-S2, AOS-027b-S3; owning files/interfaces above | AOS-027b-TC01, AOS-027b-TC02, AOS-027b-TC03, AOS-027b-TC04; parameterize every condition in this clause |
| AOS-027b-AC01 | Two independently passing worker trees whose integrated result fails tests must be rejected. A stale/fenced result cannot enter the integrated candidate; overlapping changes require an explicit reviewed resolution and fresh check run. | AOS-027b-S1, AOS-027b-S2, AOS-027b-S3; owning files/interfaces above | AOS-027b-TC01, AOS-027b-TC02, AOS-027b-TC03, AOS-027b-TC04; parameterize every condition in this clause |
| AOS-027b-AC02 | Rebase changes candidate hash: old approval invalid. Inject lost response after mock merge: no duplicate merge; unresolved state requires reconciliation. | AOS-027b-S1, AOS-027b-S2, AOS-027b-S3; owning files/interfaces above | AOS-027b-TC01, AOS-027b-TC02, AOS-027b-TC03, AOS-027b-TC04; parameterize every condition in this clause |
| AOS-027b-AC03 | Two-worker tree tests re-run after integration; passing isolated suites insufficient when combined result fails. | AOS-027b-S1, AOS-027b-S2, AOS-027b-S3; owning files/interfaces above | AOS-027b-TC01, AOS-027b-TC02, AOS-027b-TC03, AOS-027b-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-027b-S1](cursor/prompts/AOS-027b-S1.md) | AOS-027a, AOS-026 | Fenced results integrated from exact base with deterministic conflict report and no last-writer-wins. | AOS-027b-TC01; command/report/exit, immutable evidence and diff |
| [AOS-027b-S2](cursor/prompts/AOS-027b-S2.md) | AOS-027b-S1 | Independent complete required suite on final tree and fresh effect_digest approval via existing 027a service. | AOS-027b-TC02; command/report/exit, immutable evidence and diff |
| [AOS-027b-S3](cursor/prompts/AOS-027b-S3.md) | AOS-027b-S2 | Individually-passing/combined-failing, changed-base/stale approval/lost receipt fixtures and B-1 final-tree evidence. | AOS-027b-TC01, AOS-027b-TC02, AOS-027b-TC03, AOS-027b-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-027b-TC01 | integration | `tests/integration/test_aos_027b.py::test_combined_candidate_failure` | Two isolated passing patches that fail combined required tests cannot complete or merge. |
| AOS-027b-TC02 | security | `tests/integration/test_aos_027b.py::test_conflict_stale_membership` | Overlapping/stale/fenced attempt never silently joins final tree; owner conflict resolution produces new candidate/evidence. |
| AOS-027b-TC03 | chaos | `tests/integration/test_aos_027b.py::test_final_approval_cas_change` | Any base/candidate/check/member/policy change invalidates approval; lost CAS receipt reconciles once. |
| AOS-027b-TC04 | live | `tests/integration/test_aos_027b.py::test_b1_verified_two_worker_build` | Both real certified workers, integrated trusted checks, final exact approval and confirmed receipt complete bounded synthetic Build. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_027b.py --junitxml=evidence/AOS-027b.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.


---

<!-- Source: plans/AOS-028-implementation-plan.md -->

# AOS-028 — React Mission Control task views, approvals and event replay: implementation plan

**Release:** R3. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-005, AOS-014, AOS-017, AOS-023, AOS-027b. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](testing/TEST_EXECUTION.md) and [source spec](specification/specs/AOS-028.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

A locally served dashboard shows Ask, Delegate and Build intake, real task state, source evidence, worker fleet and exact pending approvals without creating a second state machine.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/api/openapi_export.py` — owning implementation file; reconcile existing code before creating it.
- `apps/mission-control/src/api/client.ts` — owning implementation file; reconcile existing code before creating it.
- `apps/mission-control/src/hooks/useTaskEvents.ts` — owning implementation file; reconcile existing code before creating it.
- `apps/mission-control/src/views/Intake.tsx` — owning implementation file; reconcile existing code before creating it.
- `apps/mission-control/src/views/GoalDetail.tsx` — owning implementation file; reconcile existing code before creating it.
- `apps/mission-control/src/views/Approvals.tsx` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `GeneratedOpenAPIClient request/response enums`
- `useTaskEvents(goalId, initialCursor) -> CanonicalViewState`
- `ApprovalPreviewView.submit(current_effect_digest, decision) -> Pending|Receipt`

**Migration ownership:** No new authoritative UI state tables; use kernel API/DB and existing sessions.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-028-F01 | React/Vite typed client generated from OpenAPI; goal/task list and detail, event timeline, approval inbox, artifact/diff/test evidence and three distinct inputs. Focus keyboard/accessible minimal workflows before graphs. | AOS-028-S1, AOS-028-S2, AOS-028-S3; owning files/interfaces above | AOS-028-TC01, AOS-028-TC02, AOS-028-TC03, AOS-028-TC04; parameterize every condition in this clause |
| AOS-028-F02 | SSE with event cursors, reconnect/backfill and idempotent reducer; reconcile with canonical API after reconnect. Handle unknown/RECONCILING/approval states explicitly, never optimistic display of COMPLETED. | AOS-028-S1, AOS-028-S2, AOS-028-S3; owning files/interfaces above | AOS-028-TC01, AOS-028-TC02, AOS-028-TC03, AOS-028-TC04; parameterize every condition in this clause |
| AOS-028-F03 | Host/origin/CSRF and local authorization integrated with AOS-009; hide Restricted content from unauthorized client context; safe markdown/source rendering and no executable HTML. | AOS-028-S1, AOS-028-S2, AOS-028-S3; owning files/interfaces above | AOS-028-TC01, AOS-028-TC02, AOS-028-TC03, AOS-028-TC04; parameterize every condition in this clause |
| AOS-028-F04 | Optional trace links to Phoenix and display accessible vs observed egress, unknown usage not $0. | AOS-028-S1, AOS-028-S2, AOS-028-S3; owning files/interfaces above | AOS-028-TC01, AOS-028-TC02, AOS-028-TC03, AOS-028-TC04; parameterize every condition in this clause |
| AOS-028-AC01 | Browser reconnect midway through workflow shows all events exactly once in UI. | AOS-028-S1, AOS-028-S2, AOS-028-S3; owning files/interfaces above | AOS-028-TC01, AOS-028-TC02, AOS-028-TC03, AOS-028-TC04; parameterize every condition in this clause |
| AOS-028-AC02 | Approval preview mismatch or stale digest blocks submission; task remains pending on network errors. | AOS-028-S1, AOS-028-S2, AOS-028-S3; owning files/interfaces above | AOS-028-TC01, AOS-028-TC02, AOS-028-TC03, AOS-028-TC04; parameterize every condition in this clause |
| AOS-028-AC03 | Keyboard navigation/contrast and no secret content in URL/logs; cross-origin mutation denied. | AOS-028-S1, AOS-028-S2, AOS-028-S3; owning files/interfaces above | AOS-028-TC01, AOS-028-TC02, AOS-028-TC03, AOS-028-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-028-S1](cursor/prompts/AOS-028-S1.md) | AOS-005, AOS-014, AOS-017, AOS-023, AOS-027b | React/TypeScript/Vite same-origin shell, generated API types and accessible Ask/Delegate/Build intake with authoritative snapshot views. | AOS-028-TC01; command/report/exit, immutable evidence and diff |
| [AOS-028-S2](cursor/prompts/AOS-028-S2.md) | AOS-028-S1 | Task/fleet/timeline/evidence/approval UI and decimal-cursor SSE reducer with bounded reconnect/retention resync. | AOS-028-TC02; command/report/exit, immutable evidence and diff |
| [AOS-028-S3](cursor/prompts/AOS-028-S3.md) | AOS-028-S2 | Synthetic browser E2E for stale approvals/errors/auth/redaction/markdown/keyboard and operator UX evidence. | AOS-028-TC01, AOS-028-TC02, AOS-028-TC03, AOS-028-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-028-TC01 | e2e | `tests/e2e/test_aos_028.py::test_ui_reconnect_authoritative` | Mid-run reconnect restores every unique event and final snapshot; >2^53 cursor exact; UI cannot invent completed state. |
| AOS-028-TC02 | security | `tests/e2e/test_aos_028.py::test_ui_approval_auth_markdown` | Stale digest prevents submit; expired session clears private view; active HTML/dangerous links and foreign origin mutation rejected. |
| AOS-028-TC03 | e2e | `tests/e2e/test_aos_028.py::test_three_intakes_and_failures` | Ask/Delegate/Build each has usable input/status/evidence; pending/error/UNKNOWN/refusal shown accurately. |
| AOS-028-TC04 | e2e | `tests/e2e/test_aos_028.py::test_keyboard_focus_evidence_preview` | Keyboard/focus/contrast and exact action evidence preview allow owner decision; no secret content in URLs/logs. |

After tests exist, baseline command is `uv run --frozen pytest tests/e2e/test_aos_028.py --junitxml=evidence/AOS-028.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.


---

<!-- Source: plans/AOS-029-implementation-plan.md -->

# AOS-029 — OTel/Phoenix tracing, cost/usage confidence and exposure dashboard: implementation plan

**Release:** R3. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-012, AOS-014, AOS-028. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](testing/TEST_EXECUTION.md) and [source spec](specification/specs/AOS-029.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

A user can trace every relevant model/tool decision and inspect what data was authorized or accessible to cloud workers versus observed network traffic, without leaking secrets.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/telemetry/tracing.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/telemetry/redaction.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/telemetry/usage.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/telemetry/exposure.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/api/routes/usage.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/api/routes/audit.py` — owning implementation file; reconcile existing code before creating it.
- `apps/mission-control/src/views/Usage.tsx` — owning implementation file; reconcile existing code before creating it.
- `apps/mission-control/src/views/Exposure.tsx` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `TelemetryExporter.emit(redacted_span) -> ExportStatus`
- `UsageService.view(actor, period) -> ConfidenceUsageReport`
- `ExposureService.view(actor, task_id) -> ExposureReport`

**Migration ownership:** Safe usage/audit/export metadata; reuse canonical route/task/check/effect correlation, no raw credentials/prompt logging.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-029-F01 | Emit OTel traces (task/attempt/policy/route/check) with privacy-aware sampling; run Phoenix locally as optional service in Compose and ensure AgentOS works if Phoenix down. | AOS-029-S1, AOS-029-S2, AOS-029-S3; owning files/interfaces above | AOS-029-TC01, AOS-029-TC02, AOS-029-TC03, AOS-029-TC04; parameterize every condition in this clause |
| AOS-029-F02 | Usage/cost labels known, estimated, unknown; separate plan quota estimates and actual paid API/overage; reconcile provider errors and account limits only by officially supported paths. | AOS-029-S1, AOS-029-S2, AOS-029-S3; owning files/interfaces above | AOS-029-TC01, AOS-029-TC02, AOS-029-TC03, AOS-029-TC04; parameterize every condition in this clause |
| AOS-029-F03 | Exposure view shows accessible manifest for encrypted remote CLI workspace, explicit authorized payload policy and OS/network observed metadata, with provider and consent reference. | AOS-029-S1, AOS-029-S2, AOS-029-S3; owning files/interfaces above | AOS-029-TC01, AOS-029-TC02, AOS-029-TC03, AOS-029-TC04; parameterize every condition in this clause |
| AOS-029-F04 | Ensure no raw tokens, excluded paths, credentials or arbitrary full prompt bodies in telemetry, even on exception. | AOS-029-S1, AOS-029-S2, AOS-029-S3; owning files/interfaces above | AOS-029-TC01, AOS-029-TC02, AOS-029-TC03, AOS-029-TC04; parameterize every condition in this clause |
| AOS-029-AC01 | Synthetic secret injected in prompt/env never appears in Phoenix/log/event; export disable has no effect on correctness. | AOS-029-S1, AOS-029-S2, AOS-029-S3; owning files/interfaces above | AOS-029-TC01, AOS-029-TC02, AOS-029-TC03, AOS-029-TC04; parameterize every condition in this clause |
| AOS-029-AC02 | Unknown provider token usage remains unknown; no '$0' fallback in UI. Encrypted CLI egress report says accessible vs observed, not guessed payload. | AOS-029-S1, AOS-029-S2, AOS-029-S3; owning files/interfaces above | AOS-029-TC01, AOS-029-TC02, AOS-029-TC03, AOS-029-TC04; parameterize every condition in this clause |
| AOS-029-AC03 | Can trace one goal through task→worker→verifier→approval across restart. | AOS-029-S1, AOS-029-S2, AOS-029-S3; owning files/interfaces above | AOS-029-TC01, AOS-029-TC02, AOS-029-TC03, AOS-029-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-029-S1](cursor/prompts/AOS-029-S1.md) | AOS-012, AOS-014, AOS-028 | Local OTel/Phoenix transport with explicit privacy/redaction/sampling and task/attempt/policy/check/effect correlation. | AOS-029-TC01; command/report/exit, immutable evidence and diff |
| [AOS-029-S2](cursor/prompts/AOS-029-S2.md) | AOS-029-S1 | Known/estimated/unknown cash/native-plan summaries and authorized/accessible/observed exposure UI/API. | AOS-029-TC02; command/report/exit, immutable evidence and diff |
| [AOS-029-S3](cursor/prompts/AOS-029-S3.md) | AOS-029-S2 | Synthetic secret/exception payload/exporter-down fixtures, trace linkage across restart and actual local footprint report. | AOS-029-TC01, AOS-029-TC02, AOS-029-TC03, AOS-029-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-029-TC01 | security | `tests/integration/test_aos_029.py::test_telemetry_secret_sentinels` | Synthetic prompt/env/token/path sentinel never appears in logs/events/Phoenix even exception paths. |
| AOS-029-TC02 | contract | `tests/integration/test_aos_029.py::test_unknown_usage_exposure_ui` | Unknown token/quota/cash never shown as zero; workspace accessible vs observed encrypted egress explained correctly. |
| AOS-029-TC03 | chaos | `tests/integration/test_aos_029.py::test_phoenix_down_no_truth_loss` | Export disabled/unavailable leaves task/approval/evidence correctness and durable event history unchanged. |
| AOS-029-TC04 | live | `tests/integration/test_aos_029.py::test_local_trace_resource_footprint` | Goal→task→worker→verifier→approval trace linkage across restart in pinned local Phoenix; report actual idle/peak footprint. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_029.py --junitxml=evidence/AOS-029.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.


---

<!-- Source: plans/AOS-030-implementation-plan.md -->

# AOS-030 — A-1/D-1/B-1 acceptance, chaos and two-week dogfood gate: implementation plan

**Release:** R3. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-017, AOS-018, AOS-019, AOS-020, AOS-021, AOS-022, AOS-023, AOS-024, AOS-025, AOS-026, AOS-027b, AOS-028, AOS-029. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](testing/TEST_EXECUTION.md) and [source spec](specification/specs/AOS-030.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

AgentOS proves three independent end-user workflows and its security/recovery invariants over a recorded two-week trial before claiming complete initial MVP.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `testing/gates.py` — owning implementation file; reconcile existing code before creating it.
- `testing/manifests.py` — owning implementation file; reconcile existing code before creating it.
- `testing/dogfood.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/cli/gates.py` — owning implementation file; reconcile existing code before creating it.
- `operations/release_review.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `GateRunner.run(release, expected_case_manifest) -> ReleaseEvidenceManifest`
- `GateEvaluator.evaluate(evidence, required_cases, compatibility) -> Pass|Incomplete|Fail`
- `MvpReview.record(owner, candidate_sha, evidence_sha, decision) -> ReviewRecord`

**Migration ownership:** Versioned release gate/trial/review records referencing immutable artifacts; feature promotion stored separately from SOTA authorization.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-030-F01 | Create immutable gate manifest referencing each fixture/test run, component version, hardware, provider, sandbox profile and approval evidence. A-1 offline Ask (ten prompts and source-linked recall); D-1 verified research with malicious web fixtures; B-1 crash-safe two-worker Build with hostile configs. | AOS-030-S1, AOS-030-S2, AOS-030-S3; owning files/interfaces above | AOS-030-TC01, AOS-030-TC02, AOS-030-TC03, AOS-030-TC04; parameterize every condition in this clause |
| AOS-030-F02 | Execute six fault drills: ambiguous external effect, prompt injection, exhausted entitlement, GPU pressure, false-done and approval-change-after-crash. Also test independent trust/privacy/autonomy mutations and reboots. | AOS-030-S1, AOS-030-S2, AOS-030-S3; owning files/interfaces above | AOS-030-TC01, AOS-030-TC02, AOS-030-TC03, AOS-030-TC04; parameterize every condition in this clause |
| AOS-030-F03 | Record task completion, user corrections, approval burdens, refusal reasons, disk/resource pressure and verified data egress. Run 14 days daily under consented personal scope, distinguishing blockers from deferred features. | AOS-030-S1, AOS-030-S2, AOS-030-S3; owning files/interfaces above | AOS-030-TC01, AOS-030-TC02, AOS-030-TC03, AOS-030-TC04; parameterize every condition in this clause |
| AOS-030-F04 | Every failed P0 security gate blocks release; confidence summaries avoid unjustified numerical significance on small N. | AOS-030-S1, AOS-030-S2, AOS-030-S3; owning files/interfaces above | AOS-030-TC01, AOS-030-TC02, AOS-030-TC03, AOS-030-TC04; parameterize every condition in this clause |
| AOS-030-AC01 | All required fixture tests pass without network escape, duplicate external effects or false-completion. | AOS-030-S1, AOS-030-S2, AOS-030-S3; owning files/interfaces above | AOS-030-TC01, AOS-030-TC02, AOS-030-TC03, AOS-030-TC04; parameterize every condition in this clause |
| AOS-030-AC02 | Two-week observed period shows no confirmed policy or task-state integrity breach; incidents root-caused with regression tests. | AOS-030-S1, AOS-030-S2, AOS-030-S3; owning files/interfaces above | AOS-030-TC01, AOS-030-TC02, AOS-030-TC03, AOS-030-TC04; parameterize every condition in this clause |
| AOS-030-AC03 | Unverified provider features and known missing hardware outcomes documented rather than green. | AOS-030-S1, AOS-030-S2, AOS-030-S3; owning files/interfaces above | AOS-030-TC01, AOS-030-TC02, AOS-030-TC03, AOS-030-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-030-S1](cursor/prompts/AOS-030-S1.md) | AOS-017, AOS-018, AOS-019, AOS-020, AOS-021, AOS-022, AOS-023, AOS-024, AOS-025, AOS-026, AOS-027b, AOS-028, AOS-029 | Immutable release evidence manifest and strict required-case evaluator; no missing/skipped/mock-live outcome can green a gate. | AOS-030-TC01; command/report/exit, immutable evidence and diff |
| [AOS-030-S2](cursor/prompts/AOS-030-S2.md) | AOS-030-S1 | A-1/D-1/B-1 suites, six fault drills, axis/security/reboot/restore matrix against one pinned MVP candidate. | AOS-030-TC02; command/report/exit, immutable evidence and diff |
| [AOS-030-S3](cursor/prompts/AOS-030-S3.md) | AOS-030-S2 | Fourteen-day consented owner trial, incident regressions/revalidated candidate, explicit accept/reject and separate SOTA decision. | AOS-030-TC01, AOS-030-TC02, AOS-030-TC03, AOS-030-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-030-TC01 | contract | `tests/e2e/test_aos_030.py::test_gate_missing_skip_unknown` | Gate refuses required missing/SKIP/NOT_RUN/UNKNOWN or wrong candidate/version/mock-for-live; CI exit zero alone insufficient. |
| AOS-030-TC02 | chaos | `tests/e2e/test_aos_030.py::test_six_required_fault_drills` | Ambiguous effect, injection, exhausted quota, GPU pressure, false done and changed approval after crash show defined safe outcomes. |
| AOS-030-TC03 | live | `tests/e2e/test_aos_030.py::test_mvp_three_journeys_conformance` | Observed A-1/D-1/B-1, independent policy axes, install/reboot/restore and actual adapter/hardware proofs all present. |
| AOS-030-TC04 | live | `tests/e2e/test_aos_030.py::test_fourteen_day_owner_acceptance` | Versioned daily-use evidence and resolved blockers for 14-day trial; owner decision references exact candidate/evidence, SOTA remains separately authorized. |

After tests exist, baseline command is `uv run --frozen pytest tests/e2e/test_aos_030.py --junitxml=evidence/AOS-030.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.


---

<!-- Source: testing/TEST_EXECUTION.md -->

# Test execution and evidence design

All scenario groups are PLANNED/NOT_RUN. Cursor creates their real assertions with each slice. test-catalog.json supplies IDs/node paths/lanes/expected behavior; requirement-traceability.json retains exact source clauses; implementation-slices.json supplies selected work. Documentation validation is not application test success.

## Lanes and fixtures

Unit/contract use pure logic/fake transports. Migration/integration use real disposable PostgreSQL. Security/chaos exercise actual OS/process/DB boundaries with synthetic fixtures; E2E covers CLI/browser paths. Live requires actual supported hardware/vendor/provider/account conformance under scoped consent. Mocked JSONL or fake transport cannot satisfy a live case. CI lacking an OS capability records SKIP; promotion still needs evidence from a certified runner/host.

Fixture families: tiny Python candidate repo and protected acceptance bundle; two owners/projects/contracts; stable-key fake effect service with lost responses; signal barriers around DB commit/process start/blob finalize/approval/Git CAS; synthetic credential sentinels and hostile configs; hermetic resolver/connector/redirect/compression/MIME/Unicode sources; ten Ask questions/five adverse briefs/10–20 reviewed MVP tasks; sanitized vendor streams; browser session/SSE/digest/unsafe-markdown fixtures.

No internet in deterministic CI; no actual host credentials or metadata endpoints in attack fixtures. Fake resolver/transport is unit evidence, not OS network evidence. Protected required tests are immutable to the worker. Candidate code still executes only in no-secret/no-network verifier sandbox.

## Planned commands after implementation

~~~text
uv lock --check
uv sync --frozen
uv run --frozen ruff check .
uv run --frozen mypy src/panestria
uv run --frozen lint-imports --config .importlinter
uv run --frozen pytest -m 'not live' --junitxml=evidence/ci.xml
uv run --frozen pytest -m 'security or chaos' --junitxml=evidence/boundaries.xml
uv run --frozen pytest -m live --junitxml=evidence/live.xml
~~~

The live command is a future separately scoped action. Register markers and gate_case_id/candidate_commit/fixture_digest through pytest user_properties. Test collection must include each required ID, with every required parameter assertion passing. Empty suite, duplicate IDs, skipped/xfail or missing cases cannot turn green because a command exited 0. Place lane-specific files as needed and update node paths in the implementation manifest.

## Gate evaluator contract

Input: required manifest, actual JUnit/structured report receipts, candidate/environment/corpus hashes, compatibility manifests and known blockers. Validate against schemas/case-result.schema.json; check every required case exists, exact candidate/version/hash, correct lane and LIVE vs HERMETIC/OS_BOUNDARY mode, command exit and immutable report/artifact proof. FAIL for failed case/blocker; INCOMPLETE for missing/SKIP/NOT_RUN/UNKNOWN/wrong candidate/mock-for-live. PASS only for complete actual evidence. Case-result text supplied by an LLM is not a trusted test runner receipt.

Version each scenario's parameters and assertion→requirement IDs; splitting a group preserves release requirements. Run changed/dependency checks per slice, cumulative G0/G1/G2/G3 at promotion, all MVP tests/six faults before trial. After changed candidate revalidate affected/cross-cutting gates and document/extend or restart observation. Report sample size/abstention/confusion honestly.

## Gates and owner review

G0: synthetic workflow/contract/state/events/approval/DB recovery. G1: A-1 offline Ask, B-single and actual sandbox/adapter/resource/auth proof. G2: D-1 with deterministic evidence plus separate support/uncertainty and live public brief. G3: B-1 two actual workers/final-tree checks, Mission Control, redacted traces/usage/exposure, cumulative security/recovery and trial.

Six faults: ambiguous external effect, prompt injection, exhausted entitlement, GPU/resource pressure, false done and approval changed after crash. R3 requires 14-day consented daily use with incident regressions resolved and exact candidate tracked. Owner acceptance and SOTA authorization remain separate. Latency targets are set from hardware evidence before acceptance; no retroactive hiding of failed targets.


---

<!-- Source: operations/RUNBOOK-AND-RELEASE.md -->

# Operational implementation and release runbook

Implement diagnostics/recovery with their owning slices. Commands are planned contracts, not currently available application operations.

| Situation | Observe | Safe action | Prohibited shortcut |
|---|---|---|---|
| Restart | workflow/task/attempt/boot receipts | Create datasource before launch, recover, inspect unfinished effects | Phantom completion or duplicate paid spawn |
| DB unavailable | bounded readiness and correlation | Refuse new writes/admission; reconnect without losing truth | Memory-only authoritative status |
| Stale worker | epoch/heartbeat/process identity | Fence publishes and observe/reconcile old effect | Old callback overwriting new attempt |
| Approval waiting | exact digest/continuation/expiry/policy | Re-preview and resume dispatch vs finalize correctly | Reuse for changed action/base/candidate |
| CAS response lost | effect/base/candidate/destination receipt | Stable protected-ref query or RECONCILING | Blind repeated/forced merge |
| Corrupt/orphan artifact | SHA and live DB refs | Refuse bad evidence, cleanup proven orphan after TTL | Path existence as success or arbitrary root traversal |
| Model OOM/pressure | actual model/resource snapshot | Stop admissions, unload/degrade, preserve state | Restricted cloud fallback |
| Auth/quota/version | safe mode/manifest/error | Disable affected capability/cooldown; owner official repair | Credential extraction/account pooling/hot-loop |
| Search/reader failure | query/redirect/source status | Incomplete/setup-required; retained denial | Guess missing evidence/silent provider switch |
| Phoenix down | bounded export status | Turn off export, keep DB truth intact | Trace system deciding task state |
| Cancel | task/attempt/in-flight effect | Stop new actions now, terminate boundedly, reconcile | CANCELLED from signal request alone |
| Upgrade/restore | consistent app+DBOS backup/manifests | Isolated restore; effects reviewed before launch | Blind remote replay or destructive downgrade |

Record commands/exit/reports/hashes/candidate/environment and mock-vs-live modes. Known non-blockers have owner/priority/follow-up; required safety/integrity/functionality failures cannot be waived into PASS.

Fourteen-day trial records date/candidate/task kind/verified result/human acceptance/corrections/approval burden/resources/egress/refusals/incidents. Scope is explicit; no unapproved employer/private data. Candidate-changing fixes revalidate tests and extend/restart relevant observation. Owner accepts/rejects exact candidate/evidence; separate record authorizes SOTA implementation. Maintain accepted MVP and rollback while deciding advanced work.
