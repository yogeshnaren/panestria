# AOS-002 — Goal contracts, tasks, attempts and database migration v1: implementation plan

**Release:** R0. **Format:** full; shared design supplies cross-component detail. **Implementation:** S1 contracts, S2 kernel schema, and S3 scoped services observed. **Tests:** TC01 hermetic; TC02, TC03, and TC04 on disposable PostgreSQL; not a release pass. **Depends on:** AOS-001. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-002.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

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
| [AOS-002-S1](../cursor/prompts/AOS-002-S1.md) | AOS-001 | Strict GoalContract and seven canonical acceptance variants; canonical monetary/hash serialization and legacy rejection fixtures. | AOS-002-TC01; command/report/exit, immutable evidence and diff |
| [AOS-002-S2](../cursor/prompts/AOS-002-S2.md) | AOS-002-S1 | Alembic domain schema, composite owner/project/task/contract constraints, closed states, optimistic versions and append-only contract guards. | AOS-002-TC02; command/report/exit, immutable evidence and diff |
| [AOS-002-S3](../cursor/prompts/AOS-002-S3.md) | AOS-002-S2 | Scoped repository/service mutations, DAG validation, idempotency conflict handling and state/event concurrency tests. | AOS-002-TC01, AOS-002-TC02, AOS-002-TC03, AOS-002-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-002-TC01 | contract | `tests/contract/test_aos_002.py` | Canonical roundtrip hash stable; edited contract creates new version; raw command, legacy discriminator, bool budget and duplicate check IDs rejected. |
| AOS-002-TC02 | migration | `tests/integration/test_aos_002_migration.py` | Migration applies and restore/reapply works; wrong project/owner/task-contract linkage, orphan attempts and invalid states rejected by SQL. |
| AOS-002-TC03 | integration | `tests/integration/test_aos_002_services.py::test_concurrent_transition_and_cursor` | Two mutations with same row_version produce one winner; global task/goal cursor commit order and rollback gaps are safe. |
| AOS-002-TC04 | security | `tests/integration/test_aos_002_services.py::test_foreign_scope_and_mass_assignment` | Foreign goal/read/write returns scoped denial; client approved_by/policy booleans and unknown executable fields rejected. |

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
