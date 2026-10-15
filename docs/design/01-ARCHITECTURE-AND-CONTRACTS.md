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

The [DDL blueprint](02-DATABASE-AND-MIGRATIONS.md) and design/schema-blueprint.sql guide Alembic; they are not an executed migration. Use one physical PostgreSQL database: app schema panestria, DBOS-managed schema(s) dbos. DBOS manages its own migrations; application Alembic never alters DBOS internals. R0 app relations have explicit principal/project/goal/contract/task/attempt bindings; composite foreign keys prevent attaching a contract/attempt/approval to a different task or project.

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

## Active personal-platform revision 3

[The normative delta](../specification/architecture/05-PERSONAL-PLATFORM-REVISION-3.md) owns the new profile/classification, style/model, connection, progress, quota/capture, phone, resource and reuse contracts. They extend existing policy/durability/evidence interfaces; no separate authoritative task store or task-state enum is introduced. [ADR 0003](../../adr/0003-personal-platform-classification.md) selects the canonical classification and legacy transition; implementation is pending. Preserve old goal/schema semantics and historical evidence through forward compatibility. R3 pretrial readiness requires 156 registered cases; AOS-030-TC04 then records the trial/owner decision, and final G3 requires all 157.
