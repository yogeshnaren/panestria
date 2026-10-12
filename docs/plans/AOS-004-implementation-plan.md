# AOS-004 — Synthetic worker, isolated Git workspace and deterministic verification: implementation plan

**Release:** R0. **Format:** checklist; shared design supplies cross-component detail. **Implementation:** S1 through S3 observed. **Tests:** TC01 through TC04 on a real worktree, process group, and disposable PostgreSQL; not a release pass. **Depends on:** AOS-003. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-004.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

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
| AOS-004-OP01 | Record worktree owner, TTL, cleanup outcome, disk use and orphan detection. Cleanup cannot traverse a symlink beyond the sandbox root. | AOS-004-S3; `src/panestria/sandbox/worktree.py` | AOS-004-TC04 retains a live worktree, removes an expired one, and leaves symlink targets outside the sandbox in place. |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-004-S1](../cursor/prompts/AOS-004-S1.md) | AOS-003 | Synthetic repo/worktree adapter lifecycle and scripted success/bad-path/hung/crash modes; bounded process handle/output. | AOS-004-TC01; command/report/exit, immutable evidence and diff |
| [AOS-004-S2](../cursor/prompts/AOS-004-S2.md) | AOS-004-S1 | Reviewed command registry and independent required test bundle; exact diff checks and immutable artifact ingress outside worker write scope. | AOS-004-TC02; command/report/exit, immutable evidence and diff |
| [AOS-004-S3](../cursor/prompts/AOS-004-S3.md) | AOS-004-S2 | False-done/tampered evidence/symlink/timeout/cancel/orphan cleanup fixtures and repeatable synthetic demo receipt. | AOS-004-TC01, AOS-004-TC02, AOS-004-TC03, AOS-004-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-004-TC01 | integration | `tests/integration/test_aos_004.py::test_mock_success_and_repeat` | Same seeded fixture yields same verdict and hashes; worker done creates only a candidate until independent checks pass. Scripted events name the attempt and epoch and do not accept the candidate. An unknown mode starts no process. |
| AOS-004-TC02 | security | `tests/integration/test_aos_004.py::test_bad_path_and_tampered_checks` | Off-scope path/symlink or altered protected mandatory test bundle fails; new worker tests cannot replace required checks. An executable mode on an otherwise allowed path is denied. A staged index change is denied when the worktree copy matches the base. Git push and a hook path other than `/dev/null` do not start. A false test claim that writes `README.md` fails, and the report keeps that path and the exit code. |
| AOS-004-TC03 | chaos | `tests/integration/test_aos_004.py::test_hung_process_and_output` | Wall watchdog times out silent process, drains bounded streams and confirms process group termination or UNKNOWN. |
| AOS-004-TC04 | chaos | `tests/integration/test_aos_004.py::test_artifact_partial_publish` | Corrupt/partial blob denied; crash after finalize before DB ref leaves only a recoverable orphan, never passed evidence. Expired worktree cleanup records owner, TTL, and disk use, copies regular files into the store before deletion, and does not follow a directory symlink. A journey report is published at the stored lease epoch, and a later epoch publishes nothing. An older attempt is not reused. Its candidate and workflow link do not count for the current attempt. |

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
