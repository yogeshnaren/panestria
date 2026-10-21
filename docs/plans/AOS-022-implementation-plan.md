# AOS-022 — Claim-support adjudication, contradiction and uncertainty labeling: implementation plan

**Release:** R2. **Format:** full; shared design supplies cross-component detail. **Implementation:** IN_PROGRESS (corpus and model preflight). **Tests:** component observations below; item/release acceptance NOT_RUN. **Depends on:** AOS-021, AOS-016. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

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

## Human-label preflight preparation (2026-10-16)

The [versioned entailment preflight](../design/34-HUMAN-LABEL-ENTAILMENT-PREFLIGHT.md)
contains 36 calibration and36 separate qualification cases from the public
human-labeled SNLI1.0 corpus, with original source snapshots, revision checksums,
unchanged text, disjoint normalized premises and CC BY-SA4.0 attribution. Input
projection omits gold/row metadata. Pure scoring retains UNKNOWN and refuses
missing/foreign predictions; zero-denominator precision remains unknown.

At 3a9067f, 14 provenance/projection/synthetic-metric checks PASS, source-bound in
evidence/entailment-corpus-2026-10-16. This is **not actual model calibration** or
AOS022 acceptance. Caption-domain/annotation/contamination/small-sample limits are
explicit. Actual privacy-conforming model observations, research-specific partial/
opinion/conflict/injection checks, independent-family conditions and calibrated
uncertainty remain required. Fixture preparation provides no training grant.

## Actual local-model outcome (2026-10-16)

[The bounded offline probe](../design/35-LOCAL-ENTAILMENT-OBSERVATION.md) uses the
existing read-only Qwen2.5:1.5b-instruct cache in actual network-none/nonroot Docker.
At bf3cb42, 24 corpus/protocol guards and two actual fold-observation checks pass.
This is an infrastructure result: **automatic support quality is NOT QUALIFIED**.
The held-out fold got21/36 labels correct and12/24 supported judgments correct
(50% supported precision); all72 recorded model calls produced closed verdicts.
The model's incorrect certainty cannot authorize support or task acceptance.

Evidence/local-entailment-2026-10-16 retains exact predictions/metrics/hashes,
tokens and runtime limits. An earlier reporting serialization failure is retained
separately; its unrecorded case count/metrics remain unknown. Source/family/privacy
and corpus/domain limits apply. No cloud inference, credentials, downloads or
training were used. Semantic integration stays unassessed pending a suitable
validated verifier; no model switch or higher privilege is implicit in this result.

## Actual public subscription preflight (2026-10-16)

At9892769, the [fixed PUBLIC-only native probe](../design/36-PUBLIC-NATIVE-ENTAILMENT-PROBE.md)
has118 protocol/tamper/process/corpus guards and two actual subscription batch
observations. Claude Haiku4.5 scored31/36 calibration and33/36 held-out; held-out
support precision12/13 (92.3%), **one falseSUPPORTED**. These small caption-domain
results do not authorize automatic research support or certify AOS022/G2.

Evidence/native-entailment-2026-10-16 retains predictions, metrics, exact source/
binary/rubric/corpus hashes and two earlier rejected launches. Explicit disabled
setting sources/skills/MCP/hooks/memory/instructions were needed beyond safe-mode;
no allowlist was widened. Both completed batches observed no overage/API key.
Actual cash/remaining quota and inference count of rejected launches stay unknown.
No SDK/private claim/training/provider fallback. Current files are contracts/
research_claims.py, execution/research_claims.py, verification/entailment.py and
execution/{entailment_probe,native_entailment_probe}.py; the earlier owning-file
list is design intent, to reconcile before semantic integration. Research-domain
human review/conflict/opinion/injection, policy/grant/disclosure and deterministic
source checks remain prerequisites; ClaimStore support remains NOT_ASSESSED.

## Owner draft review component (2026-10-21)

[Exact owner claim review](../testing/OWNER_CLAIM_REVIEW.md) connects retained
drafts/passages to explicit per-claim judgments and immutable corrections.
This is partial S3 delivery, with provenance OWNER_REPORTED and no automatic
semantic qualification, task completion or training authority. The retained
draft remains unchanged. [Connected evidence](../../evidence/owner-claim-review-2026-10-21/report.json)
records real PG/CAS/reader/CLI checks with an explicit model fixture; actual
research-domain calibration, independent-role conditions and full G2 remain open.
