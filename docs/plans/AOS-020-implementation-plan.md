# AOS-020 — Quarantined web reader and immutable source provenance: implementation plan

**Release:** R2. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-013, AOS-019. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-020.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

Every Delegate result is grounded in immutable fetched source snapshots processed by a sandboxed reader that has no privileged outbound-action tools.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/research/reader.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/research/extract.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/sandbox/profiles.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/sandbox/artifact_ingress.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `ReaderWorker.extract(snapshot_input, limits) -> ExtractedTextCandidate`
- `ExtractorRegistry.select(mime, version) -> Extractor`
- `ReaderBroker.finalize(output, source_ref) -> SnapshotRef`

**Migration ownership:** Extractor/output provenance and immutable protected text artifacts in research schema.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-020-F01 | Implement read-only `ReaderWorker` process/container with only fetch API capability; convert approved HTML/plain-text documents to normalized text with source ID, canonical URL, content hash, extractor version and passage offsets. | AOS-020-S1, AOS-020-S2, AOS-020-S3; owning files/interfaces above | AOS-020-TC01, AOS-020-TC02, AOS-020-TC03, AOS-020-TC04; parameterize every condition in this clause |
| AOS-020-F02 | Segregate reader from synthesis worker, which gets structured text observations not executable page instructions; reader has no private mounts, Git repo, secrets, agent provider auth or general tool dispatch. | AOS-020-S1, AOS-020-S2, AOS-020-S3; owning files/interfaces above | AOS-020-TC01, AOS-020-TC02, AOS-020-TC03, AOS-020-TC04; parameterize every condition in this clause |
| AOS-020-F03 | Reject truncated/malformed extract rather than claim complete source; record content limitations for tables/PDF/scripted sites. Avoid open-ended crawling; bound max pages, bytes and depth. | AOS-020-S1, AOS-020-S2, AOS-020-S3; owning files/interfaces above | AOS-020-TC01, AOS-020-TC02, AOS-020-TC03, AOS-020-TC04; parameterize every condition in this clause |
| AOS-020-AC01 | Every displayed citation resolves to a retained source snapshot. Corrupt/changed source hash causes refusal. | AOS-020-S1, AOS-020-S2, AOS-020-S3; owning files/interfaces above | AOS-020-TC01, AOS-020-TC02, AOS-020-TC03, AOS-020-TC04; parameterize every condition in this clause |
| AOS-020-AC02 | Malicious webpage asks for shell command/exfil: no actor gets request and no privileged tool invoked. | AOS-020-S1, AOS-020-S2, AOS-020-S3; owning files/interfaces above | AOS-020-TC01, AOS-020-TC02, AOS-020-TC03, AOS-020-TC04; parameterize every condition in this clause |
| AOS-020-AC03 | Extraction truncation and nontext document yield explicit incomplete evidence; duplicate URL fetches create versioned snapshots. | AOS-020-S1, AOS-020-S2, AOS-020-S3; owning files/interfaces above | AOS-020-TC01, AOS-020-TC02, AOS-020-TC03, AOS-020-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-020-S1](../cursor/prompts/AOS-020-S1.md) | AOS-013, AOS-019 | Read-only no-network reader process and bounded HTML/plain-text extractor; separate privileged fetch/synthesis principals. | AOS-020-TC01; command/report/exit, immutable evidence and diff |
| [AOS-020-S2](../cursor/prompts/AOS-020-S2.md) | AOS-020-S1 | Sanitized immutable text/provenance output through ingress, no arbitrary file writes/JS/actor tools. | AOS-020-TC02; command/report/exit, immutable evidence and diff |
| [AOS-020-S3](../cursor/prompts/AOS-020-S3.md) | AOS-020-S2 | Injection/parser/bomb/duplicate/truncation fixtures and offline replay with exact source-hash trace. | AOS-020-TC01, AOS-020-TC02, AOS-020-TC03, AOS-020-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-020-TC01 | security | `tests/integration/test_aos_020.py::test_reader_injection_no_actor` | Page tells reader to read secret/send/shell; tools and OS deny, no actor privilege handed to synthesizer. |
| AOS-020-TC02 | contract | `tests/integration/test_aos_020.py::test_mime_html_sanitization` | HTML/text extract only, no active JS/HTML; unsupported PDF/table/truncation explicit incomplete. |
| AOS-020-TC03 | chaos | `tests/integration/test_aos_020.py::test_reader_limits_bomb` | Oversized/decompression/parser CPU/hang bounded and reader stopped; protected store rejects partial output. |
| AOS-020-TC04 | integration | `tests/integration/test_aos_020.py::test_reader_snapshot_replay` | Displayed source resolves exact retained body/version; duplicate URL fetch versions preserved, changed hash denied. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_020.py --junitxml=evidence/AOS-020.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

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
