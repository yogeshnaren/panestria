# AOS-027a — Single-worker verification and protected merge approval: implementation plan

**Release:** R1. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-004, AOS-009, AOS-010. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-027a.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

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
| [AOS-027a-S1](../cursor/prompts/AOS-027a-S1.md) | AOS-004, AOS-009, AOS-010 | Independent protected command/check bundle on exact single-worker candidate; allowed/forbidden diff and artifact/verifier hashes. | AOS-027a-TC01; command/report/exit, immutable evidence and diff |
| [AOS-027a-S2](../cursor/prompts/AOS-027a-S2.md) | AOS-027a-S1 | Effect_digest preview includes owner/project/base/destination/check/policy/expiry; one-use consumption and protected ref CAS. | AOS-027a-TC02; command/report/exit, immutable evidence and diff |
| [AOS-027a-S3](../cursor/prompts/AOS-027a-S3.md) | AOS-027a-S2 | False done, tampered tests, changed base/rebase, lost merge response and single-worker gate report. | AOS-027a-TC01, AOS-027a-TC02, AOS-027a-TC03, AOS-027a-TC04; command/report/exit, immutable evidence and diff |

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
