# AOS-014 — OpenTelemetry correlation, canonical event replay and SSE: implementation plan

**Release:** R1. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-003, AOS-012. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-014.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

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
| [AOS-014-S1](../cursor/prompts/AOS-014-S1.md) | AOS-003, AOS-012 | Propagate goal/task/attempt/epoch/trace IDs and redacted local spans through transactions/adapters/verifiers. | AOS-014-TC01; command/report/exit, immutable evidence and diff |
| [AOS-014-S2](../cursor/prompts/AOS-014-S2.md) | AOS-014-S1 | Post-commit event notification with DB-backed paginated SSE replay, expiry checks, bounded buffers and decimal cursors. | AOS-014-TC02; command/report/exit, immutable evidence and diff |
| [AOS-014-S3](../cursor/prompts/AOS-014-S3.md) | AOS-014-S2 | Disconnect/duplicate/retention/>2^53/redaction fixtures and exporter-outage correctness proof. | AOS-014-TC01, AOS-014-TC02, AOS-014-TC03, AOS-014-TC04; command/report/exit, immutable evidence and diff |

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
