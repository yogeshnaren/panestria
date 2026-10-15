# AOS-011 — Source-linked personal memory schema and five-stage use events: implementation plan

**Release:** R1. **Format:** full; shared design supplies cross-component detail. **Implementation:** IN_PROGRESS. **Tests:** PARTIAL; scoped recall and real DB restore observed. **Depends on:** AOS-002. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-011.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

Offline Ask can retrieve owner/project-scoped memory with provenance, while every retrieval stage creates audit-ready data for later measurable personalization.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/memory/store.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/memory/search.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/memory/use_events.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/memory/context.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/memory/lifecycle.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/repositories/memory.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `MemoryStore.add_or_revise(actor, source, fact, expected_revision) -> MemoryRevision`
- `MemorySearch.retrieve(actor, query, limit, now) -> ProvenanceResults`
- `MemoryUseRecorder.record(observer, stage, context_ref, confidence) -> UseEvent`
- `MemoryLifecycle.suppress(actor, memory_id) -> SuppressionReceipt`

**Migration ownership:** 0003_memory: memory_item/source/revision/use_event/context_pack with scope, labels, validity, pin, suppression, retention and FTS index.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-011-F01 | Create normalized `memory_item`, `memory_source`, `memory_revision`, `memory_use_event` and optional `context_pack` tables, owner/project/privacy/provenance/validity and retention fields. R1 starts with PostgreSQL full-text search, deterministic ranking baseline; pgvector optional with model-version metadata. | AOS-011-S1, AOS-011-S2, AOS-011-S3; owning files/interfaces above | AOS-011-TC01, AOS-011-TC02, AOS-011-TC03, AOS-011-TC04; parameterize every condition in this clause |
| AOS-011-F02 | Record distinct `retrieved`, `included`, `used_by_worker`, `judged_unused`, `candidate_helped` stages with source/observer/confidence; do not auto-equate inclusion with use or successful task with causality. | AOS-011-S1, AOS-011-S2, AOS-011-S3; owning files/interfaces above | AOS-011-TC01, AOS-011-TC02, AOS-011-TC03, AOS-011-TC04; parameterize every condition in this clause |
| AOS-011-F03 | Restrict memory writes to user-submitted facts or verified explicit task outputs in R1; model-inferred changes proposed for approval. No automatic deletion based on unvalidated utility score. | AOS-011-S1, AOS-011-S2, AOS-011-S3; owning files/interfaces above | AOS-011-TC01, AOS-011-TC02, AOS-011-TC03, AOS-011-TC04; parameterize every condition in this clause |
| AOS-011-F04 | Protect memory from cross-owner/project leakage through application checks and, if feasible, PostgreSQL row-level security tests. Retrieval returns source IDs and relevance explanations. | AOS-011-S1, AOS-011-S2, AOS-011-S3; owning files/interfaces above | AOS-011-TC01, AOS-011-TC02, AOS-011-TC03, AOS-011-TC04; parameterize every condition in this clause |
| AOS-011-AC01 | Query returns correct project-local preference and evidence; another project's secret cannot appear, even through semantic similarity. | AOS-011-S1, AOS-011-S2, AOS-011-S3; owning files/interfaces above | AOS-011-TC01, AOS-011-TC02, AOS-011-TC03, AOS-011-TC04; parameterize every condition in this clause |
| AOS-011-AC02 | Five event stages each persist and survive restart, including explicit judged-unused; nonobserved stages remain unknown rather than inferred. | AOS-011-S1, AOS-011-S2, AOS-011-S3; owning files/interfaces above | AOS-011-TC01, AOS-011-TC02, AOS-011-TC03, AOS-011-TC04; parameterize every condition in this clause |
| AOS-011-AC03 | Invalid/superseded facts suppressed from current recall but lineage preserved; injection in retrieved content never upgrades policy. | AOS-011-S1, AOS-011-S2, AOS-011-S3; owning files/interfaces above | AOS-011-TC01, AOS-011-TC02, AOS-011-TC03, AOS-011-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-011-S1](../cursor/prompts/AOS-011-S1.md) | AOS-002 | Normalized source-linked memory/revisions with immutable provenance and explicit owner-approved writes. | AOS-011-TC01; command/report/exit, immutable evidence and diff |
| [AOS-011-S2](../cursor/prompts/AOS-011-S2.md) | AOS-011-S1 | Scoped FTS retrieval/validity/conflict ranking and minimal hashed context packs with bounded tokens; unknown stages remain unknown. | AOS-011-TC02; command/report/exit, immutable evidence and diff |
| [AOS-011-S3](../cursor/prompts/AOS-011-S3.md) | AOS-011-S2 | Five-stage telemetry, correction/export/suppression/retention baseline and cross-project/injection/stale-memory fixtures. | AOS-011-TC01, AOS-011-TC02, AOS-011-TC03, AOS-011-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-011-TC01 | integration | `tests/integration/test_aos_011.py::test_scoped_valid_fact_recall` | Project preference returns exact source/current revision; expired, superseded and suppressed facts absent before ranking. |
| AOS-011-TC02 | security | `tests/integration/test_aos_011.py::test_cross_project_injection` | Other owner/project data never appears; memory content cannot change policy, provider route or standing rules. |
| AOS-011-TC03 | contract | `tests/integration/test_aos_011.py::test_five_stages_unknown_attribution` | Five distinct stages persist with observer/confidence; inclusion/success never invent used/helped causality. |
| AOS-011-TC04 | integration | `tests/integration/test_memory_restore.py::test_revision_suppression_restore` | Correction creates new revision; pins retained; suppression blocks new contexts and DB restore retains lineage/suppression metadata. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_011.py --junitxml=evidence/AOS-011.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

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

## Observed backup/restore check

`tests/integration/test_memory_restore.py::test_revision_suppression_restore`
uses actual `pg_dump` and `pg_restore` against the uniquely identified R1 test
container on port 55439. It restores into a new temporary database, checks source
and revision history, privacy labels, owner pins, suppression, all five explicitly
recorded observation stages, scope denial and restored immutability constraints,
then removes only that temporary database. It does not touch the R0 review
service/database/volume or interpret unknown confidence as proof of causality.

This is a database memory restore proof. A full application backup must also
retain its protected artifact/evidence files, model/config pins and runtime
receipts; this test does not establish complete application disaster recovery.

## Revision 3 extension — MVP-X07, delivered in R3

The [active personal-platform contract](../specification/architecture/05-PERSONAL-PLATFORM-REVISION-3.md#mvp-x07) adds **Encrypted owner profile and canonical classification**. Original parent scope and historical results remain intact. These new slices deliver in **R3**, even when the parent AOS item originally ships in R1; they do not reopen historical G0 acceptance or fabricate G1 evidence. Inspect the current repository before choosing exact new files/migration revisions.

| Slice | Concrete outcome, narrowed to about one developer-day | Prerequisites |
| --- | --- | --- |
| AOS-011-S4 | Resolve classification compatibility with an audited forward migration and fail-closed legacy handling. | AOS-007-S3, AOS-011-S3 |
| AOS-011-S5 | Implement bounded encrypted profile read/write through the local broker and safe context selection. | AOS-011-S4, AOS-009-S3 |
| AOS-011-S6 | Complete key lifecycle, restore, correction/suppression and cross-scope boundary checks. | AOS-011-S5 |

Implementation checkpoints: the [key adapter](../testing/PROFILE_KEYS.md) and
[ciphertext storage](../testing/PROFILE_VAULT.md) are bounded foundations.
Source-bound component results do not complete these slice envelopes. Profile
API/context dispatch stays disabled until its exact admission and runtime
privacy boundary is qualified; old memory does not migrate silently into profiles.

Use the [revision-3 slice handoff](../cursor/prompts/MVP-REV3-SLICE.md) with the selected manifest entry. File ownership candidates are in implementation-slices.json; record an ADR for a material change. Existing shared transaction/security/API requirements still apply.

| Added case | Lane | Required passing behavior |
| --- | --- | --- |
| AOS-011-TC05 | security | Goal, policy, source and derived classifications use PUBLIC/INTERNAL/CONFIDENTIAL/RESTRICTED consistently; UNKNOWN denies; legacy PRIVATE remains restricted pending an audited explicit resolution. |
| AOS-011-TC06 | security | Profile ciphertext and associated-data identity resist tampering/cross-owner/project access; restricted plaintext never enters general FTS, logs, worker mounts or prohibited outbound payloads. |
| AOS-011-TC07 | integration | Locked/missing key store denies profile operations; approved key rotation and encrypted backup/restore preserve usable data without co-locating wrapping keys. |
| AOS-011-TC08 | integration | Owner correction, suppression, expiry and forgetting remove the profile from newly compiled contexts and account for derivatives and backup limits. |

These nodes and scenarios are planned, not observed tests. Register real assertion/node/lane/evidence mappings while implementing; missing required evidence blocks G3. Rollout begins disabled, uses synthetic content until its boundary is certified, stops admissions on failure and preserves audit/receipts. R4-R7 work is not authorized by completing this extension.

S4 is delivered incrementally: first the restrictive legacy interpretation and
cloud guard, then audited forward migration and versioned canonical interfaces,
then complete database/source/destination compatibility proof. See the
[classification rollout](../design/06-CLASSIFICATION-COMPATIBILITY-ROLLOUT.md).
The first guard alone cannot complete S4 or TC05; S5/S6 remain blocked on the
complete classification boundary.
