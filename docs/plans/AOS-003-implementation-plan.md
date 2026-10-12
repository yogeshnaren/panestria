# AOS-003 — DBOS-backed durable single-task execution and recovery: implementation plan

**Release:** R0. **Format:** full; shared design supplies cross-component detail. **Implementation:** S1 atomic admission, S2 replay, and S3 restore observed. **Tests:** TC01 through TC04 on disposable PostgreSQL; not a release pass. **Depends on:** AOS-002. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

**Current technical validation:** G0 PASS on `d457242e9e6ee2c54fbd99db99cb35319b1c8783`; all R0 cases observed, including fresh Ubuntu. Owner acceptance remains pending. See [completion](../reviews/R0-TECHNICAL-COMPLETION.md). Earlier status lines below are historical.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-003.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

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
| AOS-003-OP01 | Structured logs with goal/task/workflow ID; observe unfinished workflows, retry counts, and recovery latency. | AOS-003-S3; `src/panestria/execution/recovery.py` | AOS-003-TC02 lists PENDING and ENQUEUED workflows with goal, task, and recovery attempts, and the recover line carries the same ids. |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-003-S1](../cursor/prompts/AOS-003-S1.md) | AOS-002 | Pin/probe datasource session/isolation/launch and client enqueue-in-transaction; commit admission atomically with app request and scoped workflow ID. | AOS-003-TC01; command/report/exit, immutable evidence and diff |
| [AOS-003-S2](../cursor/prompts/AOS-003-S2.md) | AOS-003-S1 | Replay-deterministic task workflow with tracked state/event callbacks and separate external-effect steps; duplicate starts resolve existing identity. | AOS-003-TC02; command/report/exit, immutable evidence and diff |
| [AOS-003-S3](../cursor/prompts/AOS-003-S3.md) | AOS-003-S2 | Signal-barrier crash/recovery harness and app+DBOS backup/restore drill; publish recovered/failed diagnostics without speculative completion. | AOS-003-TC01, AOS-003-TC02, AOS-003-TC03, AOS-003-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-003-TC01 | integration | `tests/integration/test_aos_003.py::test_atomic_enqueue_and_duplicate` | Concurrent duplicate requests produce one task/workflow; rollback of admission yields neither task nor enqueue. |
| AOS-003-TC02 | chaos | `tests/integration/test_aos_003.py::test_before_after_commit` | Kill before DB commit rolls back all app writes; kill after tracked commit before return replays one transition/event, no callback side effect. Unfinished workflows are listed with goal, task, workflow, and recovery attempts. A workflow body that calls the clock is rejected. An attempt whose lease epoch does not match the task does not move it or start the worker. |
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
