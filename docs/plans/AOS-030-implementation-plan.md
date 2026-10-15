# AOS-030 — A-1/D-1/B-1 acceptance, chaos and two-week dogfood gate: implementation plan

**Release:** R3. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-017, AOS-018, AOS-019, AOS-020, AOS-021, AOS-022, AOS-023, AOS-024, AOS-025, AOS-026, AOS-027b, AOS-028, AOS-029. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-030.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

AgentOS proves three independent end-user workflows and its security/recovery invariants over a recorded two-week trial before claiming complete initial MVP.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `testing/gates.py` — owning implementation file; reconcile existing code before creating it.
- `testing/manifests.py` — owning implementation file; reconcile existing code before creating it.
- `testing/dogfood.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/cli/gates.py` — owning implementation file; reconcile existing code before creating it.
- `operations/release_review.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `GateRunner.run(release, expected_case_manifest) -> ReleaseEvidenceManifest`
- `GateEvaluator.evaluate(evidence, required_cases, compatibility) -> Pass|Incomplete|Fail`
- `MvpReview.record(owner, candidate_sha, evidence_sha, decision) -> ReviewRecord`

**Migration ownership:** Versioned release gate/trial/review records referencing immutable artifacts; feature promotion stored separately from SOTA authorization.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-030-F01 | Create immutable gate manifest referencing each fixture/test run, component version, hardware, provider, sandbox profile and approval evidence. A-1 offline Ask (ten prompts and source-linked recall); D-1 verified research with malicious web fixtures; B-1 crash-safe two-worker Build with hostile configs. | AOS-030-S1, AOS-030-S2, AOS-030-S3; owning files/interfaces above | AOS-030-TC01, AOS-030-TC02, AOS-030-TC03, AOS-030-TC04; parameterize every condition in this clause |
| AOS-030-F02 | Execute six fault drills: ambiguous external effect, prompt injection, exhausted entitlement, GPU pressure, false-done and approval-change-after-crash. Also test independent trust/privacy/autonomy mutations and reboots. | AOS-030-S1, AOS-030-S2, AOS-030-S3; owning files/interfaces above | AOS-030-TC01, AOS-030-TC02, AOS-030-TC03, AOS-030-TC04; parameterize every condition in this clause |
| AOS-030-F03 | Record task completion, user corrections, approval burdens, refusal reasons, disk/resource pressure and verified data egress. Run 14 days daily under consented personal scope, distinguishing blockers from deferred features. | AOS-030-S1, AOS-030-S2, AOS-030-S3; owning files/interfaces above | AOS-030-TC01, AOS-030-TC02, AOS-030-TC03, AOS-030-TC04; parameterize every condition in this clause |
| AOS-030-F04 | Every failed P0 security gate blocks release; confidence summaries avoid unjustified numerical significance on small N. | AOS-030-S1, AOS-030-S2, AOS-030-S3; owning files/interfaces above | AOS-030-TC01, AOS-030-TC02, AOS-030-TC03, AOS-030-TC04; parameterize every condition in this clause |
| AOS-030-AC01 | All required fixture tests pass without network escape, duplicate external effects or false-completion. | AOS-030-S1, AOS-030-S2, AOS-030-S3; owning files/interfaces above | AOS-030-TC01, AOS-030-TC02, AOS-030-TC03, AOS-030-TC04; parameterize every condition in this clause |
| AOS-030-AC02 | Two-week observed period shows no confirmed policy or task-state integrity breach; incidents root-caused with regression tests. | AOS-030-S1, AOS-030-S2, AOS-030-S3; owning files/interfaces above | AOS-030-TC01, AOS-030-TC02, AOS-030-TC03, AOS-030-TC04; parameterize every condition in this clause |
| AOS-030-AC03 | Unverified provider features and known missing hardware outcomes documented rather than green. | AOS-030-S1, AOS-030-S2, AOS-030-S3; owning files/interfaces above | AOS-030-TC01, AOS-030-TC02, AOS-030-TC03, AOS-030-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-030-S1](../cursor/prompts/AOS-030-S1.md) | AOS-017, AOS-018, AOS-019, AOS-020, AOS-021, AOS-022, AOS-023, AOS-024, AOS-025, AOS-026, AOS-027b, AOS-028, AOS-029 | Immutable release evidence manifest and strict required-case evaluator; no missing/skipped/mock-live outcome can green a gate. | AOS-030-TC01; command/report/exit, immutable evidence and diff |
| [AOS-030-S2](../cursor/prompts/AOS-030-S2.md) | AOS-030-S1 | A-1/D-1/B-1 suites, six fault drills, axis/security/reboot/restore matrix against one pinned MVP candidate. | AOS-030-TC02; command/report/exit, immutable evidence and diff |
| [AOS-030-S3](../cursor/prompts/AOS-030-S3.md) | AOS-030-S2 | Fourteen-day consented owner trial, incident regressions/revalidated candidate, explicit accept/reject and separate SOTA decision. | AOS-030-TC01, AOS-030-TC02, AOS-030-TC03, AOS-030-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-030-TC01 | contract | `tests/e2e/test_aos_030.py::test_gate_missing_skip_unknown` | Gate refuses required missing/SKIP/NOT_RUN/UNKNOWN or wrong candidate/version/mock-for-live; CI exit zero alone insufficient. |
| AOS-030-TC02 | chaos | `tests/e2e/test_aos_030.py::test_six_required_fault_drills` | Ambiguous effect, injection, exhausted quota, GPU pressure, false done and changed approval after crash show defined safe outcomes. |
| AOS-030-TC03 | live | `tests/e2e/test_aos_030.py::test_mvp_three_journeys_conformance` | Observed A-1/D-1/B-1, independent policy axes, install/reboot/restore and actual adapter/hardware proofs all present. |
| AOS-030-TC04 | live | `tests/e2e/test_aos_030.py::test_fourteen_day_owner_acceptance` | Versioned daily-use evidence and resolved blockers for 14-day trial; owner decision references exact candidate/evidence, SOTA remains separately authorized. |

After tests exist, baseline command is `uv run --frozen pytest tests/e2e/test_aos_030.py --junitxml=evidence/AOS-030.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

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

## Revision 3 extension — MVP-X14, delivered in R3

The [active personal-platform contract](../specification/architecture/05-PERSONAL-PLATFORM-REVISION-3.md#mvp-x14) adds **Reuse, REA evidence and comparative engineering**. Original parent scope and historical results remain intact. These new slices deliver in **R3**, even when the parent AOS item originally ships in R1; they do not reopen historical G0 acceptance or fabricate G1 evidence. Inspect the current repository before choosing exact new files/migration revisions.

| Slice | Concrete outcome, narrowed to about one developer-day | Prerequisites |
| --- | --- | --- |
| AOS-030-S4 | Record reuse/REA decision and comparative fixture provenance in the existing evidence model. | AOS-008-S3, AOS-025-S3 |
| AOS-030-S5 | Verify selected integrations/parity and include all revised obligations in release evaluation. | AOS-030-S4, AOS-028-S6, AOS-012-S7, AOS-018-S5, AOS-017-S6, AOS-025-S5 |

Use the [revision-3 slice handoff](../cursor/prompts/MVP-REV3-SLICE.md) with the selected manifest entry. File ownership candidates are in implementation-slices.json; record an ADR for a material change. Existing shared transaction/security/API requirements still apply.

| Added case | Lane | Required passing behavior |
| --- | --- | --- |
| AOS-030-TC05 | contract | Material reuse/recreation records choose a source or REA artifact/runtime evidence route, pin target/tool identity and preserve evidence, limits, license/provenance and minimum integrated scope. |
| AOS-030-TC06 | security | REA findings inherit privacy labels and trusted execution boundaries; available source uses normal inspection per its workflow, and artifact analysis cannot grant live target execution or credential access. |
| AOS-030-TC07 | integration | Adopted components pass behavior/contract/security/resource parity and rollback checks; representative Ask/Delegate/Build/style comparisons report actual sample size and verified-success cost without unsupported SOTA claims. |

These nodes and scenarios are planned, not observed tests. Register real assertion/node/lane/evidence mappings while implementing; missing required evidence blocks G3. Rollout begins disabled, uses synthetic content until its boundary is certified, stops admissions on failure and preserves audit/receipts. R4-R7 work is not authorized by completing this extension.
