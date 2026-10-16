# AOS-013 — Research source snapshots, hashes, passage spans and claim evidence: implementation plan

**Release:** R2. **Format:** full; shared design supplies cross-component detail. **Implementation:** IN_PROGRESS (data contracts, pure text byte checks, durable request metadata and protected bytes). **Tests:** 79 contract/text + 13 actual request + 34 protected-filesystem checks PASS; full item cases NOT_RUN. **Depends on:** AOS-002, AOS-008. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-013.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

Current narrow task implements [closed research data contracts](../design/17-RESEARCH-SOURCE-CONTRACTS.md). Pydantic validation does not establish actual fetch, artifact integrity, byte-boundary, verifier or source authority. The follow-on [canonical text and supplied byte checker](../design/19-RESEARCH-TEXT-BYTES.md) adds strict UTF-8/Unicode 15 NFC, exact hashes/length and multibyte offsets. It only returns BYTE_MATCH_ONLY. Request metadata now has [immutable scoped PostgreSQL storage](../design/20-RESEARCH-REQUEST-STORAGE.md) with same-transaction event publication. The [scoped protected byte store](../design/22-RESEARCH-PROTECTED-BLOBS.md) now verifies capped bytes with private stable descriptors, process-crash retry and bounded locking. Source/claim schema, retained fetch, protected artifact lookup, reader and semantic judgments remain pending. No full AOS-013 case is promoted by these component checks.

A research claim is traceable to an actual retained and fetched source, with exact text offset and source content hash, not just a URL in generated prose.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/contracts/research.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/research/sources.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/research/extract.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/research/claims.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/repositories/research.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `SourceStore.commit_fetch(actor, receipt, raw_blob, text_blob) -> SnapshotRef`
- `PassageResolver.resolve(snapshot_ref, start_offset, end_offset) -> VerifiedPassage`
- `ClaimStore.attach_evidence(actor, claim_ref, passages) -> ClaimEvidence`

**Migration ownership:** Request metadata is implemented in 0023_research_request; remaining source/claim metadata uses the next additive revision after 0023; historical prospective label `0005_research`: research_request/source_snapshot/claim/claim_passage/verification_report; raw/text hashes, extraction/offset versions and scope.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-013-F01 | Schema `research_source_snapshot` includes request URL, verified terminal URL, redirects, timestamp, status, type, byte limit, SHA-256 raw fetch hash, normalized text hash, extractor version, privacy class and encrypted/protected store key. | AOS-013-S1, AOS-013-S2, AOS-013-S3; owning files/interfaces above | AOS-013-TC01, AOS-013-TC02, AOS-013-TC03, AOS-013-TC04; parameterize every condition in this clause |
| AOS-013-F02 | Retain source text with stable UTF-8 offsets and extractor-specific mapping to original bytes where possible; passages referenced as `(source_id,start,end,normalization_version)`. | AOS-013-S1, AOS-013-S2, AOS-013-S3; owning files/interfaces above | AOS-013-TC01, AOS-013-TC02, AOS-013-TC03, AOS-013-TC04; parameterize every condition in this clause |
| AOS-013-F03 | `claim_evidence` stores claim text/hash, one-to-many source passage refs, quote-match status, support verdict, conflict set and source-fetch errors. | AOS-013-S1, AOS-013-S2, AOS-013-S3; owning files/interfaces above | AOS-013-TC01, AOS-013-TC02, AOS-013-TC03, AOS-013-TC04; parameterize every condition in this clause |
| AOS-013-F04 | Canonical source IDs only minted by trusted reader, not model text; static corpus fixtures for redirects, corrupted/truncated content, table extraction ambiguity. | AOS-013-S1, AOS-013-S2, AOS-013-S3; owning files/interfaces above | AOS-013-TC01, AOS-013-TC02, AOS-013-TC03, AOS-013-TC04; parameterize every condition in this clause |
| AOS-013-AC01 | Invalid source ID, missing passage, offset outside snapshot, changed source body, and fabricated URL all rejected. | AOS-013-S1, AOS-013-S2, AOS-013-S3; owning files/interfaces above | AOS-013-TC01, AOS-013-TC02, AOS-013-TC03, AOS-013-TC04; parameterize every condition in this clause |
| AOS-013-AC02 | Exact-quote fixture passes only when normalization recorded; page with truncated table marked insufficient, not invented. | AOS-013-S1, AOS-013-S2, AOS-013-S3; owning files/interfaces above | AOS-013-TC01, AOS-013-TC02, AOS-013-TC03, AOS-013-TC04; parameterize every condition in this clause |
| AOS-013-AC03 | Fetch records immutable; claim verdict references explicit extractor version and source hash. | AOS-013-S1, AOS-013-S2, AOS-013-S3; owning files/interfaces above | AOS-013-TC01, AOS-013-TC02, AOS-013-TC03, AOS-013-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-013-S1](../cursor/prompts/AOS-013-S1.md) | AOS-002, AOS-008 | Immutable source/claim/Pydantic schema and Alembic metadata, protected raw/text artifact refs. | AOS-013-TC01; command/report/exit, immutable evidence and diff |
| [AOS-013-S2](../cursor/prompts/AOS-013-S2.md) | AOS-013-S1 | Canonical NFC UTF-8 text and half-open byte passage offsets; explicit charset/truncation/version semantics. | AOS-013-TC02; command/report/exit, immutable evidence and diff |
| [AOS-013-S3](../cursor/prompts/AOS-013-S3.md) | AOS-013-S2 | Hash/source/scope/offset fabrication fixtures and offline stored-evidence reconstruction. | AOS-013-TC01, AOS-013-TC02, AOS-013-TC03, AOS-013-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-013-TC01 | migration | `tests/integration/test_aos_013.py::test_research_scope_integrity` | Wrong project/goal/source/claim linkage fails; immutable fetch rows cannot silently overwrite extractor version. |
| AOS-013-TC02 | contract | `tests/integration/test_aos_013.py::test_utf8_offsets_hashes` | Non-ASCII passage offsets validate byte boundaries; out-of-range/split character/hash mismatch rejected. |
| AOS-013-TC03 | security | `tests/integration/test_aos_013.py::test_fabricated_source_reference` | Model-generated URL/ID without broker-retained successful fetch cannot pass evidence resolution. |
| AOS-013-TC04 | integration | `tests/integration/test_aos_013.py::test_snapshot_versions_truncation` | Changed body/re-extraction creates new snapshot; truncated content stays incomplete and never invents missing table text. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_013.py --junitxml=evidence/AOS-013.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

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

A [PUBLIC HTTPS transport](../design/27-RESEARCH-PUBLIC-FETCH-TRANSPORT.md) now
returns bounded memory-only bytes with fresh all-public DNS and exact verified
TLS peers on every redirect, framing/body/deadline/cancellation bounds and no
cookies/proxies/auth/compression/retries. At ecf564f, 178 targeted checks pass;
three actual public TLS checks pass at 3c1b3a2 with identical fetch code, including
an actual IANA downgrade denial. Injected DNS/TLS fixtures are labeled separately.
Source-bound results and the earlier wrong expectation remain in
evidence/research-public-fetch-2026-10-15. This does not persist a source, mint
source IDs, authorize fetch or make a passage/claim usable. Scoped source/claim
schema, retained receipt/artifact lookup, isolated reader and citation authority
remain pending; no full AOS-013 case or G2 promotion follows from this component.

The [isolated text/HTML reader](../design/28-ISOLATED-RESEARCH-TEXT-READER.md)
extracts strict UTF8/Unicode15 NFC with exact input/output hashes inside the
existing nonroot/read-only/network-none Docker boundary. At f60fc1a, 31 new
checks pass (14 actual container/public-TLS cases and 17 explicitly injected
receipt/controller guards), plus 134 existing research checks. Actual HTTPS
bytes feed the container reader; runtime/program/tokenizer hashes are retained.
HTML is tokenized text, with no browser CSS visibility/table/raw-byte mapping
claim. Raw cap is 2 MiB; text cap512 KiB yields explicit TRUNCATED on overflow.
PDF remains UNSUPPORTED and required next work. This is memory-only extraction;
source/claim persistence, retained provenance, SourceStore and citation authority
remain pending. Evidence: evidence/isolated-research-reader-2026-10-15.

The [PDF runtime prerequisite](../design/29-PDF-DEPENDENCY-RUNTIME-BUNDLE.md)
freezes pypdf 6.20.1/BSD-3-Clause and copies only a verified 61-file source/license
manifest to a private readonly bundle. Thirteen filesystem/import checks pass at
3bc45f, including actual Docker import/configuration. It parses no PDF input and
does not change UNSUPPORTED outcomes; actual isolated PDF integration remains
next work. Evidence: evidence/pdf-runtime-bundle-2026-10-15.
