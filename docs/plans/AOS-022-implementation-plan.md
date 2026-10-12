# AOS-022 — Claim-support adjudication, contradiction and uncertainty labeling: implementation plan

**Release:** R2. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-021, AOS-016. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-022.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

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
| [AOS-022-S1](../cursor/prompts/AOS-022-S1.md) | AOS-021, AOS-016 | Human-labeled supported/contradicted/insufficient/ambiguous/opinion corpus with explicit rubric and deterministic prerequisites. | AOS-022-TC01; command/report/exit, immutable evidence and diff |
| [AOS-022-S2](../cursor/prompts/AOS-022-S2.md) | AOS-022-S1 | Separately configured support model/role with safe local scheduling or consented eligible route; abstention and duplicate-source correlation. | AOS-022-TC02; command/report/exit, immutable evidence and diff |
| [AOS-022-S3](../cursor/prompts/AOS-022-S3.md) | AOS-022-S2 | Calibration/conflict/unavailable fixtures and owner-visible uncertainty review; preserve separation of model verdict and required human rubric-review. | AOS-022-TC01, AOS-022-TC02, AOS-022-TC03, AOS-022-TC04; command/report/exit, immutable evidence and diff |

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
