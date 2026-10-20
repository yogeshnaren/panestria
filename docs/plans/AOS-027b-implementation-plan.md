# AOS-027b — Integrated multi-worker verification and protected merge: implementation plan

**Release:** R3. **Format:** full; shared design supplies cross-component detail. **Implementation:** IN_PROGRESS. **Tests:** component observations; release scenarios NOT_RUN. **Depends on:** AOS-027a, AOS-026. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-027b.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

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
| [AOS-027b-S1](../cursor/prompts/AOS-027b-S1.md) | AOS-027a, AOS-026 | Fenced results integrated from exact base with deterministic conflict report and no last-writer-wins. | AOS-027b-TC01; command/report/exit, immutable evidence and diff |
| [AOS-027b-S2](../cursor/prompts/AOS-027b-S2.md) | AOS-027b-S1 | Independent complete required suite on final tree and fresh effect_digest approval via existing 027a service. | AOS-027b-TC02; command/report/exit, immutable evidence and diff |
| [AOS-027b-S3](../cursor/prompts/AOS-027b-S3.md) | AOS-027b-S2 | Individually-passing/combined-failing, changed-base/stale approval/lost receipt fixtures and B-1 final-tree evidence. | AOS-027b-TC01, AOS-027b-TC02, AOS-027b-TC03, AOS-027b-TC04; command/report/exit, immutable evidence and diff |

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

## Component delivery observed 2026-10-20

[Final-tree integration](../testing/FINAL_TREE_INTEGRATION.md) now collects protected completed-node handoffs, detects blob/structural conflicts, runs all original goal checks on the combined tree and reaches the existing exact owner approval/Git CAS. Component observations include individually-passing/combined-failing output and cancellation fencing; [source-bound evidence](../../evidence/final-tree-integration-2026-10-20/report.json). Real native two-worker B-1 qualification, admitted conflict resolution, all stale/changed-source and recovery scenarios remain pending; original gate case IDs are not promoted.
