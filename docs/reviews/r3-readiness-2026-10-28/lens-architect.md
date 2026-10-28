# Panestria adversarial architecture review (system design lens)

Scope: read-only audit of /home/user/panestria (src/panestria 55,281 LOC in 357 files; tests 52k LOC; 40 migrations; 483 files under docs/, 119 in docs/design/).
Method: AST import graph (scratchpad graph.py, edges.json), direct reading of kernel/events/effects/leases/admission/SSE/migrations, `lint-imports` (11/11 kept), hermetic `pytest tests/unit` (851 pass, 8 fail, 1 skip in 13.6s; all 8 failures are host-environment sensitive: native proxy platform, GPU startup, pid-namespace memory probe, bootstrap pin guards).
Marking: CONFIRMED = read in code / reproduced by script. PLAUSIBLE = follows from code but not exercised.

---------------------------------------------------------------------------
## 0. Scores (1-10, anchored)

| Dimension | Score | Justification |
|---|---|---|
| Architecture & system design | 6 | Kernel primitives are genuinely strong: caller-owned transactions, CAS leases with epochs, single approval fingerprint, `enqueue_in_transaction` (DBOS workflow enqueued in the same tx as state+event+idempotency row, admission.py:119-171), effect prepare/claim/finish/reconcile with epoch fencing. But DBOS durability only covers the synthetic R0 workflow; the MVP Build/Delegate paths are in-process daemon threads with manual reconciliation. Docs are stale vs code. |
| Modularity / boundaries | 5 | 11 contracts kept, but they are almost all "not API/CLI" rules. No layering contract. 8 packages form one dependency SCC (kernel/memory/learning/resources/inference/sandbox/verification/config_storage). 46 cross-module imports of underscore-private names, incl. SSRF/egress predicates. Features are smeared across 6 horizontal layers (research = 38 files / 6.6k LOC in 7 packages). |
| Durability / reliability design | 6 | Atomicity and fencing primitives are right (ADR 0002 lock makes seq order == commit order for task_event). Gaps: no automatic outbox relay/sweeper, no resumable workflow for Build/Research, task state machine enforced only by convention across 26 raw UPDATEs, seq handed out outside the lock for 9 side tables, permanent caps derived from immutable event history. |
| Simplicity / minimalism (strict) | 4 | R0 demo/synthetic scaffolding (about 4.5k LOC) ships in the runtime package and is a dependency of 10 production modules; 12 `config_*.py` with copy-pasted validators; 3 parallel implementations of the side_effect state machine; 3 DB access stacks (psycopg raw, SQLAlchemy engines created per call, DBOS datasource); 14 connection factories / 23 `psycopg.connect`; 119 numbered design docs for 55k LOC; 1,143 stringly-typed `KernelDenied("...")` codes. Good: little speculative abstraction (12 Protocols, mostly 2+ impls), SQL is bounded with LIMITs. |
| Efficiency / scalability (design) | 5 | Fine for one user on one box, by design. But: connection-per-call (no pool), SSE polls the DB every 100 ms and re-authenticates per event (new TCP+auth each), one global advisory lock serialises all event writers, `task_event` is queried by `kind`/`task_id` with no index (seq scans on an append-only, undeletable table), docker driven by CLI subprocess + 50 ms inspect polling. |
| Operability / observability design | 5 | Strong: typed denial envelope with correlation id, readiness probe with budget, redaction-first OTel allow-list (telemetry/tracing.py), `storage`/`metrics`/`perf` views, explicit recovery CLI. Weak: only 1 module uses `logging`; 112 `except Exception`; no metrics export; no runbook-level reconciliation automation; ARCHITECTURE.md describes a state 36 migrations ago. |

---------------------------------------------------------------------------
## 1. Findings, ranked

### P0
None found that breaks a stated safety invariant on the hot path. The closest are P1-1/P1-2 below.

### P1

**P1-1 [CONFIRMED] Durable-workflow claim is true only for the synthetic R0 path; MVP Build/Delegate are non-resumable in-process threads.**
- DBOS is imported in exactly 4 files (execution/dbos_runtime.py, task_workflow.py, recovery.py, admission.py); the only queue is `QUEUE_NAME = "panestria-synthetic"` (dbos_runtime.py:14), 6 `@DBOS.*` decorators total.
- Real Build is `MissionRunService.wake()` starting `threading.Thread(... daemon=True, name="panestria-mission-build")` inside the API process (execution/mission_run.py:49-54); module docstring: "no startup scan or background queue". native_plan.py:351 uses a ThreadPoolExecutor for the two workers. kernel/scheduler.py:3-5: "A claim remains occupied after expiry, cancellation or an unknown process outcome... no automatic retry or fallback."
- Consequence: an API restart mid-Build leaves claims occupied until an owner manually reconciles. That is a defensible safety-first choice, but it is not "durable execution" in the Temporal/DBOS/LangGraph sense, and the architecture narrative (and CLAUDE/AGENTS text) says DBOS. Operationally the owner is the recovery engine.
- Fix direction: state the contract explicitly (Tier A: DBOS-durable; Tier B: owner-reconciled), and either (a) route Build/Research through the same `enqueue_in_transaction` + step checkpointing, or (b) add a read-only "orphan sweeper" that only *reports* occupied claims and effects stuck in EXECUTING/UNKNOWN past `claim_expires_at`.

**P1-2 [CONFIRMED] `effect_outbox` is a state table, not a relay: nothing scans it.**
- `ix_outbox_due` (0006_effect_outbox.py:31) exists, but `grep` finds no reader of `effect_outbox` outside kernel/effects.py `_lock`; `EffectExecutor.dispatch/reconcile` (execution/outbox.py:43-63) are called inline only from owner_build.py:479, proposal_demo.py:843/889, never from a periodic loop. A process crash between `claim()` commit and `finish()` leaves `side_effect.state='EXECUTING'` and `task` unchanged (not RECONCILING) until someone calls `reconcile`; `begin_reconciliation` is only reachable from demo/`review_demo` and background reconcile CLI.
- The fencing itself is right (epoch bumped at claim and at begin_reconciliation, `finish` rejects `stale_dispatch`, effects.py:228-231, 285-288). The hole is liveness, not safety: ambiguous effects are never *discovered* automatically.
- Also: effects created through `kernel/repositories/approvals.py:260-270 insert_effect` and `execution/task_workflow.py:177` have **no** `effect_outbox` row, and `SideEffectService._lock` (effects.py:182-195) INNER JOINs outbox, so those effects can never go through claim/reconcile. Three creators, one consumer.
- Fix: one `EffectLedger` (create + claim + finish + reconcile + list_stuck), always creating the outbox row; add `list_stuck(now)` and surface it in `mission`/`health`.

**P1-3 [CONFIRMED] Task state machine is enforced by convention at 26 raw `UPDATE panestria.task SET state=...` sites in 15 files; no DB guard.**
- ALLOWED_TRANSITIONS (contracts/task.py:38) is consulted in 8 places (kernel/tasks.py:150, approvals.py:107/323, cancellation.py:74, plan_lifecycle.py:139, research_collection.py:252, execution/task_workflow.py:117/207). Not consulted in: kernel/effects.py:236-245/268-272 (sets RECONCILING with a terminal-state NOT IN list), kernel/build.py:535-540 (RECONCILING->VERIFYING->COMPLETED as two consecutive UPDATEs), leases.py, scheduler.py, plan_returns.py, plan_revisions.py, build_plan.py, build_merge.py, retries.py, proposal_demo.py. `grep -n "TRIGGER" migrations | grep task` finds no transition trigger (37 triggers exist, all immutability/audit).
- Not every UPDATE is CAS on `row_version`.
- Fix: one `TaskMachine.transition(uow, task_id, target, cause, expected_version)` in kernel/tasks.py that does table check + CAS + event; add a `BEFORE UPDATE OF state` trigger encoding the same table (generated from contracts/task.py so they cannot drift).

**P1-4 [CONFIRMED] `task_event` is used as a queryable state store but has only `(goal_id, seq)` and `seq` indexes.**
- Only index on the table: `ix_event_goal_seq` (0002_kernel.py:238) + partial uniques for repair drafts (0037). Queries filter by `kind` and `payload->>...`: kernel/background.py:28-35 (`kind='background.queued'` joined to goal by owner), kernel/background_run.py:312-316 (**global** anti-join: every `background.run_started` NOT EXISTS matching `run_returned` on `payload->>'run_sha256'`, no goal filter, run on every `start`), execution/research_synthesis.py:262/389/451, research_review.py:43/106, research_query_plan.py:122/130 (`WHERE task_id=%s AND kind=%s`, no task_id index), native_connection.py:28.
- The table is append-only and immutable (`immutable_event` trigger, 0013_event_audit.py:34-36; retention is a logical `floor_seq` only), so it grows without bound and these scans get monotonically slower.
- Also a design smell: domain truth (run lifecycle, withdrawal, queue membership) lives in event `kind` strings rather than in tables, so the audit log is coupled to business reads.
- Fix: add `(task_id, kind, seq)` and `(kind, goal_id)` indexes now; move run/queue lifecycle to real tables (the pattern already used for `research_request`, `build_worker_claim`).

**P1-5 [CONFIRMED code / PLAUSIBLE impact] Permanent caps computed over immutable history can wedge the feature.**
- kernel/background.py:28-35 raises `background_queue_history_limit` if the owner has >256 `background.queued` events *ever* (withdrawn items still count; events cannot be deleted); background_run.py `len(history) >= 16 -> background_run_history_limit`. There is no code path that retires them (retention floor only affects replay).
- Fix: count live rows via a table with a state column, or have retention actually archive.

### P2

**P2-1 [CONFIRMED] R0 demo/synthetic scaffolding is production-layer code and a hidden dependency of 10 modules.**
- execution/synthetic_journey.py (1,082 LOC, 1 class 764 LOC), execution/proposal_demo.py (1,006; `ProposalDemo` class 831 LOC, `_run` 174 LOC), api/proposal_demo.py (131), cli/review_demo.py (149), demo.py (288), review.py (138), brokers/harness/mock.py (370), api/serve.py (308) + task_workflow.py (518) = about 4.0k LOC of R0/demo.
- Ten production modules import `_lock/_private/_atomic` (private, underscore) *from proposal_demo*: owner_build.py:26, build_metrics.py:16, profile_qualification.py:16, native_qualification.py:26, local_repair.py:33, local_plan.py:27, background_run.py:15, native_plan.py:32, background_account.py:10, offline_build.py:20 (plus cli/review_demo.py:19). Deleting the "demo" breaks owner build.
- Fix: extract those 3 helpers (about 40 LOC) to `platform/fsutil.py` (public names), then move the demo + journey to `devkit/` (not in the wheel) or `tests/support`.

**P2-2 [CONFIRMED] Package dependency SCC and weak boundary rules.**
- Script output (package-level SCC): inference, memory, learning, sandbox, verification, kernel, resources, config_storage. Evidence edges: kernel.ask -> memory.{context,profile,profile_ask}, learning.recorder, resources.catalog, telemetry.tracing; kernel.scheduler -> resources.hardware; kernel.plans -> verification.paths; and back: learning -> kernel (8 edges), memory -> kernel (27), resources.storage_status -> kernel.{errors,goals}, sandbox.artifact_ingress -> kernel.{repositories.tasks,uow}.
- Module-level SCCs (5): kernel.{approvals,build,plan_scope,plan_store}; execution.{background_account,native_connection,offline_build,owner_build}; api.routes.{ask,profiles}; inference.{manifest,runtime}; cli.{build_browser,build_tui}.
- .importlinter has no `layers` contract and says nothing about inference/memory/learning/resources/policy/telemetry. `brokers`/`sandbox` (the untrusted-worker side) may legally import kernel (sandbox/artifact_ingress.py imports `append_event`'s module), which is wider than the stated trust boundary.
- Fix direction: add a `layers` contract: `api|cli > execution > (verification, brokers, memory, learning) > kernel > (policy, resources, sandbox-contracts) > contracts|platform`; move `artifact_ingress` (the only sandbox->kernel edge) up to `execution`; move `kernel.ask`'s memory/learning coupling to an `execution/ask` orchestration.

**P2-3 [CONFIRMED] Config sprawl is a design smell, not just a naming one.**
- 12 modules, 783 LOC, two paradigms (pydantic-settings env in config.py; JSON-file + `read_private` in 11 others) and 75 direct `os.environ`/`getenv` hits in 25 files.
- Copy-paste: token regex `[A-Za-z0-9_-]{32,128}` duplicated in config_activity.py, config_local.py, config_phone.py, config_profile.py; "absolute and resolve()==path" and "cache has only blobs/manifests, runtime not overlapping" reimplemented in config_local.py:60-70 and config_plan.py:34-45 with *different exception types* (LocalApplicationRejected vs ValueError); default port 8766 in both config_local.py:28 and config_profile.py:19 while cli/local.py:75 uses 8768; `config_model.py` is 20 LOC and `config_storage.py` 12 LOC.
- Fix: single `config/` package: `files.py` (read_private, load_token, require_absolute, require_private_dir), `env.py` (current Settings), `local.py`, `build.py`, `research.py`, `phone.py`; one `ConfigRejected(code)`.

**P2-4 [CONFIRMED] Three DB access stacks and 23 ad-hoc `psycopg.connect` calls.**
- psycopg raw SQL in 64 files; SQLAlchemy Core in 5 (events.py, admission.py, task_workflow.py, dbos_runtime.py, recovery.py); `sa.create_engine` executed 7 times, e.g. `_record_effect` builds and disposes an engine per call (execution/task_workflow.py:162-185). 14 `connect`/`_connect` factories with differing statement_timeout (2 s api/db.py:22, 5 s cli/plan.py:55, 2 s/1 s mission_run.py:36).
- Two copies of `append_event`: kernel/repositories/tasks.py:34-72 (psycopg) and kernel/repositories/events.py:15-56 (SQLAlchemy). They must stay byte-compatible on the lock tuple; today the constant is duplicated (`EVENT_LOCK` events.py:13 and `_EVENT_LOCK` in tasks.py).
- Fix: one `db.py` (`connect(role)`, small `psycopg_pool`), one `append_event` (SQLAlchemy variant becomes a thin adapter calling the psycopg path via `connection.connection`).

**P2-5 [CONFIRMED] ADR 0002 ordering guarantee covers `task_event` only; 9 side tables draw `seq` from the same sequence outside the lock.**
- `seq bigint NOT NULL UNIQUE DEFAULT nextval(pg_get_serial_sequence('panestria.task_event','seq'))` in 0023, 0024, 0025, 0026, 0027 (x3), 0039 (x2). e.g. research_requests.py:45-52 INSERTs (calls nextval, no lock) and only later calls `append_event` (which takes the lock, line about 86). Two concurrent preparers can get seq 5 (row) and 6 (event) while the seq-5 row commits after the seq-6 event is visible.
- Safe today because the side-table `seq` is only echoed in receipts (research_requests.py:21,76; research_sources.py:29,37) and nobody replays by it. It breaks the "global cursor is commit-ordered" statement the moment anyone does.
- Fix: drop the default and take seq from `append_event` return, or rename the column `ordinal` and document that it is not a cursor.

**P2-6 [CONFIRMED] SSE / replay path does O(10/s) connection setups per stream.**
- api/event_stream.py:56-77: loop `await asyncio.sleep(0.1)` then `to_thread(_page)` -> `open_database` (new TCP connection + auth, db.py:18) each iteration; plus `to_thread(authorize)` per delivered event, which for cookie sessions opens another connection (sessions.py:105-106). No LISTEN/NOTIFY though DBOS is configured with `use_listen_notify`. Max stream 30 s then client reconnect. For the phone Mission Control observer (same path) this is the dominant steady-state load.
- Replay *correctness* is fine: `max(seq)` high-water read in the same snapshot as state (event_replay.py:45-58), page bounded `seq<=high`, and ADR-0002 lock makes commit order == seq order for task_event writers. I could not find a writer that bypasses `append_event`/`append_domain_event` (only 2 `INSERT INTO panestria.task_event` sites).
- Fix: shared pool; one `NOTIFY panestria_event` in `append_event` (pg_notify is transactional, delivered at commit, so no late-commit skip) and a single listener fan-out; cache authorization per stream with expiry.

**P2-7 [CONFIRMED] Global serialisation + lock ordering by comment only.**
- Locks: EVENT_LOCK (106971,1) held until commit by every event writer; ADMISSION_LOCK (106972,1); FLEET_LOCK (726173,26) taken in at least 12 places (scheduler.py:31/51, background.py:100/323, background_run.py:40, plan_lifecycle.py:38, plan_revisions.py:45, repair_intents.py:76, mission_run route:81, local_repair.py:218...); `hashtextextended(goal)` advisory locks in goals.py:87, ask.py:82, curation.py:112, offline_build_recall.py:152; plus session lock `pg_try_advisory_lock` (execution/background_run.py:137,169). Ordering rule ("fleet lock before project/goal/task locks", scheduler.py docstring; "Callers must not write afterward", events.py:25) is documented, not enforced.
- Single-user local: throughput is fine; the risk is deadlock/long-hold regressions (PostgreSQL will detect advisory-lock deadlocks and abort one tx, which the kernel maps to a generic error) and `statement_timeout`/`lock_timeout` = 1-2 s on all API connections means contention surfaces as 5xx/`database_unavailable`, not a wait.
- Fix: a `locks.py` with named constants and a debug-mode lock-order assertion (`SELECT ... FROM pg_locks` in tests); take EVENT_LOCK in `append_event` only (already) and assert "no write after append" by wrapping UnitOfWork in a "sealed after event" flag.

**P2-8 [CONFIRMED] Three implementations of the side_effect lifecycle.** (kernel/effects.py SideEffectService; approvals.insert_effect + build.py:380-540 authorize/complete_confirmed; synthetic_journey.py:671-710 `_prepared_effect/_effect_state`; task_workflow.py:162-190 `_record_effect`). They differ in whether `effect_outbox` exists, whether `classification`/`request_ref` columns are set (approvals.py:266 omits them), and which states they can reach. See P1-2.

**P2-9 [PLAUSIBLE] Stale and over-numerous docs are an architecture-control risk.**
- docs/ARCHITECTURE.md:3-5 says "Alembic head is 0004_check_candidate" and "brokers: The mock worker only"; actual head 0040_phone_devices, brokers has claude_build/claude_proposal/research fetch/PDF workers. Package table omits inference, memory, learning, policy, resources, telemetry. 119 design docs in docs/design, 483 files in docs/ plus a phase-tracker/implementation-slices JSON set; AGENTS.md instructs agents to start from rev-3 plan. A new engineer cannot derive the real layering from the "architecture" file.

### P3

- P3-1 [CONFIRMED] 46 cross-module imports of private (underscore) names, including security predicates: `sandbox.egress._public_unicast/_verify_peer` imported by brokers/research/fetch.py:25 and execution/research_sources.py:40; `brokers.research.fetch._HttpSocket/_remaining` by search.py:23; `kernel.build._contract` by plan_returns.py:18; `api.routes.goals._api/_kick/_unavailable` by 6 routers; `api.routes.ask._transaction/_configured/_status` by 6 routers (and routes.ask <-> routes.profiles is a cycle). Fix: promote to public module `api/deps.py`, `sandbox/egress.py` public API.
- P3-2 [CONFIRMED] Very long methods: ClaudeEventParser._frame 270 LOC (event_parser.py), AdmittedNativeBuild.run 234, AskTerminal.run 227 (cli/tui.py), ProposalDemo._run 174, DockerSandbox._execute 162 (runner.py), OwnerBuild.prepare_policy 104, OwnerSynthesis.synthesize 115, BuildEvidenceService.publish 91. These are where bugs hide; they are test-covered but hard to review.
- P3-3 [CONFIRMED] Error handling is stringly typed: 1,143 `KernelDenied("code")` literals, 25 `*Denied/*Rejected/*Unavailable` exception classes, 112 `except Exception` (cli/plan.py has 18, all collapsing to one fixed JSON string at cli/plan.py:41-43, losing the reason). A `DenyCode` StrEnum plus a doc-generated table (docs/api already exports OpenAPI) would give exhaustiveness checking.
- P3-4 [CONFIRMED] Logging is effectively absent: `import logging` in 1 file (brokers/research/pdf_worker.py). All diagnostics rely on typed errors and redacted OTel spans (telemetry/tracing.py allow-lists attributes). Good privacy posture, but operators get no breadcrumb for unexpected exceptions (`except Exception` branches discard them).
- P3-5 [CONFIRMED] Docker is driven via `docker` CLI subprocesses with 50 ms inspect polling (sandbox/runner.py:323, 527); each inspect is a fork. OK for 2 workers; would not scale to many.
- P3-6 [CONFIRMED] Migrations: 40 files, 2,498 LOC, about 70 tables, 37 triggers, only about 16 explicit indexes (most access paths rely on PK/UNIQUE). All 40 define `downgrade()`, but 20+ are guarded `RuntimeError("... use forward repair or a reviewed backup")` when data exists (e.g. 0018, 0029) - i.e. effectively forward-only, which is the right call for audit tables; but it should be declared policy, not per-file. Raw-SQL migrations are readable and use `LOCK TABLE ... SHARE ROW EXCLUSIVE` around backfills (0018) - good. `migrations/schema_fingerprint.txt` exists (drift guard). Missing: an index review pass (P1-4) and a migration squash baseline (0001-0017 could collapse into one for fresh installs).
- P3-7 [CONFIRMED] CLI is thin-ish composition root, not a business-logic leak: cli/background.py, local.py, phone.py, plan.py, research.py construct kernel/execution services in-process against Postgres directly (36 kernel + 30 execution imports) rather than via the API; `_connection()` in cli/plan.py:47-57 builds its own DSN/timeouts. Dual access path (HTTP for goals/approvals/events; in-process for build/plan/research/background) means authz and idempotency are enforced by services in one path and by the API layer in the other. Acceptable (owner-local trust), but the boundary should be one `app/services.py` factory.
- P3-8 [CONFIRMED] `ops` package is 41 LOC (one function), `policy` 274 LOC, `learning` 672, `resources` 1,062: some of these are too small to be packages; `kernel/policy.py` vs `policy/` naming collision.

---------------------------------------------------------------------------
## 2. Dependency graph facts (scripted)

Package edges (module-import counts, from graph.py):
- execution -> kernel 228, contracts 138, brokers 31, verification 31, policy 30, sandbox 17 (execution is the real orchestration layer).
- kernel -> contracts 103, policy 13, memory 3, telemetry 3, resources 2, verification 1, learning 1.
- api -> kernel 83, contracts 22, memory 12, execution 10; cli -> kernel 36, contracts 32, execution 30, api 13 (cli.goals->api client types).
- brokers -> contracts 18, sandbox 6 only (clean). verification -> contracts, sandbox, policy, telemetry (clean). contracts -> nothing (clean; verified: zero outbound non-contract edges). policy -> contracts only (clean).
- Lazy (function-level) imports: 140 of 1,808 edges, used to hide cycles in api/mission_web.py and execution/*.
- Fan-in top: kernel.errors 130, kernel.uow 116, kernel.goals 106 (Actor lives in goals), config_local 44, kernel.repositories.tasks 41, kernel.repositories.policy 40, contracts.policy 37. `Actor` and `KernelDenied` are de-facto platform types parked in kernel; `contracts/` and `config*` cannot own them, which is why config_* had to grow its own exception.
- Fan-out top: execution.owner_build 35, proposal_demo 30, native_plan 28, cli.plan 26, scoped_bash 26, api.local_server 24, native_build 23, synthetic_journey 23, build_plan 23.

### Top 15 files by LOC
| LOC | File | Justified? |
|---|---|---|
| 1082 | execution/synthetic_journey.py | No: R0 scaffold; one 764-LOC class with 40 methods; move to devkit |
| 1006 | execution/proposal_demo.py | No: demo orchestration + 3 shared helpers used by 10 modules; extract helpers |
| 673 | cli/plan.py | Partly: 26 commands but 18 `except Exception`; split by sub-app (plan, repair, native) |
| 575 | sandbox/runner.py | Mostly: security-critical Docker driver; `_execute` 162 LOC should be state-machine split |
| 563 | brokers/harness/event_parser.py | `_frame` 270 LOC; table-drive it |
| 561 | cli/tui.py | `AskTerminal.run` 227 LOC; UI loop mixed with HTTP client |
| 554 | kernel/build.py | Two services (store+evidence) in one file; split |
| 541 | execution/owner_build.py | 35 imports: coordinator god-object |
| 529 | execution/research_synthesis.py | OK size, but `_sha`-style helpers duplicated |
| 518 | execution/task_workflow.py | Synthetic R0 workflow |
| 476 | cli/research.py | OK |
| 474 | kernel/background_run.py | event-kind queries (P1-4) |
| 452 | api/health.py | Probe supervisor + models; over-sized for what it does |
| 448 | execution/native_build.py | `run` 234 LOC |
| 440 | execution/scoped_bash.py | 26 imports |

---------------------------------------------------------------------------
## 3. Core-invariant verdicts

| Invariant | Verdict | Evidence |
|---|---|---|
| Atomic state+event+result in one PG tx | HOLDS for kernel paths (UnitOfWork is caller-owned, uow.py; repos never commit; `enqueue_in_transaction` in admission.py:119). Convention-only "no write after append". | events.py:25, tasks.py:34 |
| Global ordered cursor, no missed late events | HOLDS for `task_event` (advisory xact lock held to commit, then seq allocated; reader bounds `seq<=max(seq)` from same snapshot). Does NOT hold for the 9 side-table seq columns (P2-5). Throughput cost: global writer serialisation. | ADR 0002; event_replay.py:45-80 |
| Idempotency / workflow identity | HOLDS: `idempotency_record` PK(owner,project,operation,key) with request_hash compare; DBOS `workflow_id_reuse_policy: reject` + `workflow_link` row, all in the admission tx. Only 3 sites use `idempotency_record` (goals, approvals, admission), others rely on natural unique keys. | admission.py:86-171 |
| Effect outbox + reconciliation | PARTIAL: correct claim/receipt/epoch fencing; ambiguous receipt (None) -> UNKNOWN + task RECONCILING; but no discovery loop and 3 divergent creators (P1-2, P2-8). | effects.py:218-248 |
| Lease/epoch fencing | HOLDS: `lease_epoch` bump on acquire; `require_current` verifies epoch+status+expiry under row lock; reclaim marks old attempt LOST. Expiry "never proves process cancellation" (leases.py:1) so a zombie worker can still produce external effects; mitigated by CAS git updates and per-effect epochs. | leases.py:27-97 |
| Approval effect_digest binding | HOLDS: sha256 over canonical ActionPreview incl. owner, project, task, contract hash/version, policy, destination, expected_base, candidate, required_checks, minimum_actor, expiry; recomputed at prepare AND re-checked at claim; one-shot via PK on `approval_consumption`. Gap (P3): digest does not include attempt id / lease epoch / evidence-bundle id, so "approved candidate" is bound by hash only. | contracts/approval.py:19-67; effects.py:72-120 |

---------------------------------------------------------------------------
## 4. Comparison with SOTA agent runtimes

- Temporal / DBOS durable execution: Panestria *uses* DBOS correctly for the one flow where it matters most (transactional enqueue, deterministic-workflow guard `execution/determinism.py`, recovery attempt cap with FAILED receipt). It falls short because the MVP flows do not run as workflows, there is no automatic resume, and no signals/timers abstraction (approvals are polled DB rows). Exceeds: approval/effect semantics (one-shot digest-bound consumption, epoch-fenced ambiguous-effect reconciliation) are stricter than most Temporal/LangGraph apps, which leave this to the user.
- LangGraph checkpointing: Panestria has no general checkpoint/rewind of agent state; the equivalent is immutable evidence bundles + events. Better auditability (hash-chained immutable events, generated `sha256`), worse resumability and time-travel.
- OpenAI Agents SDK / Claude Agent SDK sandboxes: Panestria is well ahead on isolation depth (no-network containers, egress proxy with DNS pinning, tool gateway, binary pins, profile-key boundary enforced by import-linter) and on human-in-the-loop semantics; behind on ergonomics (no pluggable sandbox provider interface: DockerSandbox is concrete and Docker CLI-driven; no streaming tracing standard beyond a redacted OTel allow-list; no eval/replay harness for agent runs).
- Net: security/approval design meets or exceeds SOTA; durability and operability design are mid-pack; simplicity is below.

---------------------------------------------------------------------------
## 5. Structural simplification proposals (priority from coordinator)

Ranked by value/risk. LOC estimates are runtime `src/panestria` only, rounded; "gross" = lines removed from the runtime tree, "net" = after replacements.

| # | Move | Evidence | Value | Risk | Est. LOC |
|---|---|---|---|---|---|
| S1 | **Extract `_lock/_private/_atomic/_git` to a public `platform/fsutil.py`; then move synthetic_journey, proposal_demo, api/proposal_demo, cli/review_demo, demo.py, review.py, brokers/harness/mock.py, api/serve journey thread into `devkit/` (excluded from the wheel) or `tests/support`; delete `PANESTRIA_MODE=recover` demo path after R0 acceptance decision.** | 10 importers of proposal_demo privates (P2-1); R0 "not accepted" per ARCHITECTURE.md:3 so deletion needs owner decision, but the move does not. | Very high: -4k LOC from runtime, removes "demo" from the dependency of production code, shrinks the largest classes | Low for the helper extraction (mechanical); Medium for the move (tests import them) | gross -4,000; net about -3,800 |
| S2 | **Single `EffectLedger` (kernel/effects.py) absorbing approvals.insert_effect, task_workflow._record_effect, synthetic `_effect_state`, build.py effect reads; always create outbox row; add `list_stuck()`.** | P1-2, P2-8 | High (closes the liveness gap and a divergence class) | Medium (touches approval + merge flows, DB-backed tests needed) | net about -400 |
| S3 | **Single `TaskMachine.transition()` + DB trigger generated from contracts.task.ALLOWED_TRANSITIONS; replace 26 raw UPDATEs.** | P1-3 | High (invariant becomes structural) | Medium-High: 15 files; do it incrementally behind the trigger in `WARN` mode first | net about -300 |
| S4 | **Collapse `config_*.py` into a `config/` package with one `files.py` (read_private, token, path rules), one exception, one port table; delete config_model.py (20), config_storage.py (12), config_profile.py (40, subset of config_local), merge config_activity into config_local; phone extends activity.** | P2-3 | Medium-high | Low (pure functions, unit tests exist) | gross -783 -> about 420: net about -350 |
| S5 | **One `db.py`: `connect(role)`, pooled psycopg, one `append_event` (SQLAlchemy variant delegates).** Replace 23 `psycopg.connect` + 14 factories + per-call `sa.create_engine`. | P2-4, P2-6 | Medium-high (efficiency + consistency) | Low-Medium | net about -250 |
| S6 | **Add `layers` import-linter contract and fix the 5 module SCCs / 8-package SCC:** move `sandbox/artifact_ingress.py` to execution; move memory/learning/resources calls out of `kernel/ask.py` into `execution/ask` (the other kernel->{verification,resources} edges are 1-2 imports each: relocate `verification.paths` helper to contracts); promote `api/routes/{goals,ask}` shared helpers to `api/deps.py`. | P2-2, P3-1 | High for maintainability; zero runtime LOC change | Low-Medium (import moves) | 0 (improves clarity) |
| S7 | **Organise by feature inside layers:** `kernel/{core,build,research,background,ask,connections}/`, `execution/{research,build,native,background,profile}/`, `contracts/{...}` same subfolders. Rename without changing code. Research alone is 38 files / 6.6k LOC; build 27 / 5.0k; native 21 / 3.2k; plan 18 / 4.3k. | File census | High onboarding value; flat dirs of 58 (kernel) / 56 (execution) / 61 (contracts) files are unnavigable | Low (git mv + import rewrite, mechanical) | 0 |
| S8 | **Index and state-table pass for task_event reads:** add `(task_id, kind, seq)` and `(kind, goal_id)` indexes now; migrate background queue/run lifecycle to tables. | P1-4, P1-5 | High (perf + removes permanent-cap hazard) | Medium (one migration + 2 services) | net about +100 |
| S9 | **Collapse the four tiny web apps' boilerplate:** api/local_server.py (268), activity_server.py (167), profile_server.py (29), mission_web.py (227), local_web.py (24), main.py (146) each build a FastAPI app with own security middleware/lifespan/auth wiring (`FastAPI(` appears in main.py:49 and proposal_demo.py:58, rest wrap routers differently). One `create_app(profile=...)` factory with route sets by profile. | api file census | Medium | Medium (security headers/middleware must remain byte-identical; golden tests) | net about -400 |
| S10 | **De-duplicate small helpers:** 7 `_sha`, 4 `_pairs`, 4 `_read`, 3 `_private`; hashing/canonical JSON in `contracts/canonical.py` (exists as `contracts.build.canonical_sha256`; promote). Table-drive `ClaudeEventParser._frame`; split `DockerSandbox._execute` into launch/attach/settle phases. | Duplicate census | Low-Medium | Low | net about -200 |
| S11 | **Fold micro-packages:** `ops` (41 LOC) into a `devkit`/`cli`; `policy` + `kernel/policy.py` + `kernel/repositories/policy.py` into one `policy` package; `learning` (672) under `execution/learning` or `memory`; root `demo.py`/`review.py` out of root. | P3-8 | Low-Medium | Low | about -50 |
| S12 | **DenyCode StrEnum for the 1,143 `KernelDenied` literals + `except Exception` audit (112) with a single logger.** | P3-3, P3-4 | Medium | Medium (broad) | +100 / improves checkability |
| S13 | **Docs:** regenerate ARCHITECTURE.md from reality (package table from `lint-imports`/graph script, alembic head from `alembic heads`) and mark docs/design/NN as historical vs. normative; CI check that `ARCHITECTURE.md` head matches `alembic heads`. | P2-9 | Medium | None | docs only |

Estimated total: runtime `src/panestria` 55.3k -> about 49.5-50k LOC (about -10%), of which S1 is two thirds. Test code (52k) will shrink commensurately only if the R0 tests are retired.

### Proposed target layout

```
src/panestria/
  contracts/          # pure pydantic models, grouped: goal/ task/ approval/ build/ research/ plan/ memory/ native/ ...
  platform/           # config/ (env.py, files.py, local.py, build.py, research.py, phone.py), db.py (pool, connect, append_event),
                      #   errors.py (KernelDenied, DenyCode, Actor), fsutil.py, locks.py, hashing.py, tracing.py
  policy/             # engine, labels, profiles (absorbs kernel/policy.py + kernel/repositories/policy.py)
  kernel/             # transactional core only; no I/O to the outside world
    core/             # goals, tasks(TaskMachine), approvals, leases, effects(EffectLedger), cancellation, events+replay
    build/ research/ background/ connections/ plans/ ask/ ...
  sandbox/            # docker runner, egress, worktree, gitcmd  (imports platform+contracts only)
  verification/       # unchanged (clean)
  brokers/            # harness/ research/  (untrusted-side; imports contracts+sandbox only)
  inference/ memory/ learning/   # leaf services; imports platform+contracts only; kernel does not import them
  execution/          # orchestration: research/ build/ native/ background/ profile/ ask/ workflow/(dbos) ; imports everything below
  api/                # deps.py, app factory(profile), routes/
  cli/                # thin Typer wrappers over execution/ services; one services.py factory
devkit/ (outside wheel)   # synthetic_journey, proposal_demo, mock worker, demo, review_demo, r0 recovery
```
Layer rule to enforce (import-linter `layers`): `api|cli` > `execution` > `brokers|verification|memory|learning|inference` > `kernel` > `sandbox|policy` > `platform` > `contracts`.

---------------------------------------------------------------------------
## 6. What is good (credit, so the above is calibrated)
- contracts/ and policy/ are leaf-clean (zero outbound app imports); brokers/verification/sandbox have tiny, intentional fan-out.
- Queries are consistently bounded (only 2 of ~70 `fetchall()` call sites lack LIMIT, both bounded by construction); N+1 loops are capped (<=16 rows).
- Transactional enqueue, one-shot approvals, epoch-fenced effects, redaction-first telemetry, forward-only audit migrations with data-guarded downgrades, hermetic unit suite that runs in 14 s.
- Baseline per coordinator: ruff passes, mypy clean on 359 files, 11/11 import-linter contracts kept; `ruff format --check` would reformat 74 files (cosmetic, but means formatter is not a CI gate); fast suite 11 failures of 951 (my hermetic unit run: 8 failed, all environment-dependent).
