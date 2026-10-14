# AOS-006 — Lease fencing, retry bounds, outbox and external-action reconciliation: implementation plan

**Release:** R1. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-003. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-006.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

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
| [AOS-006-S1](../cursor/prompts/AOS-006-S1.md) | AOS-003 | CAS epoch/attempt leases with DB-clock expiry and heartbeat; release/reclaim fences all stale writes. | AOS-006-TC01; command/report/exit, immutable evidence and diff |
| [AOS-006-S2](../cursor/prompts/AOS-006-S2.md) | AOS-006-S1 | Transactional effect intent/outbox and single-use approval consumption; fixed classification/idempotency/receipt interfaces. | AOS-006-TC02; command/report/exit, immutable evidence and diff |
| [AOS-006-S3](../cursor/prompts/AOS-006-S3.md) | AOS-006-S2 | Bounded retry/durable backoff and response-loss reconciliation drills; cancelling cannot invent a no-effect receipt. | AOS-006-TC01, AOS-006-TC02, AOS-006-TC03, AOS-006-TC04; command/report/exit, immutable evidence and diff |

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
