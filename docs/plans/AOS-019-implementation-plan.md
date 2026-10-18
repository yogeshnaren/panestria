# AOS-019 — Search abstraction and SSRF-safe web retrieval broker: implementation plan

**Release:** R2. **Format:** full; shared design supplies cross-component detail. **Implementation:** IN_PROGRESS (fetch and explicit destination policy components). **Tests:** component evidence retained; complete item/release acceptance NOT_RUN. **Depends on:** AOS-008, AOS-009, AOS-013. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Current component continuation: [durable search admission](../design/50-DURABLE-SEARCH-ADMISSION.md)
and its [checks/limits](../testing/SEARCH_ADMISSION.md) bind the configured transport
to a fixed task-wide query budget and committed outbound disclosure. AOS-019-S1
remains IN_PROGRESS: owner-facing workflow and actual configured-provider/OS
qualification are pending. No native Build certificate is reused as web authority.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-019.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

AgentOS can search approved public web sources and fetch URLs without resolving or redirecting into internal endpoints, exposing secrets, or mixing reader and actor privileges.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/brokers/search/base.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/brokers/search/searxng.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/brokers/search/configured_api.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/research/fetch.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/sandbox/network.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `SearchProvider.search(query, policy, limits) -> SearchResults`
- `FetchBroker.fetch(actor, url, constraints) -> FetchReceipt`
- `PinnedHTTPConnector.connect(approved_ip, original_host, tls_policy) -> Connection`

**Migration ownership:** Search/fetch/redirect/egress observations and consent/account refs; raw restricted query retention disabled.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-019-F01 | Define `SearchProvider.search(query, constraints)` for configured API and optional SearXNG. Search query is off-device disclosure (including SearXNG upstream engines), recorded with consent/provider/labels. No search from Restricted tasks unless explicitly local-only index. | AOS-019-S1, AOS-019-S2, AOS-019-S3; owning files/interfaces above | AOS-019-TC01, AOS-019-TC02, AOS-019-TC03, AOS-019-TC04; parameterize every condition in this clause |
| AOS-019-F02 | `FetchBroker.fetch(url)` validates scheme, port, hostname, resolved IP sets (IPv4/IPv6), redirects, proxy bypass, content type, max bytes/time/redirects and protocol downgrade; deny private/loopback/link-local/metadata/multicast and IPv4-mapped IPv6 as appropriate. Re-resolve/validate on every redirect and connect to pinned, checked address to resist DNS rebinding. | AOS-019-S1, AOS-019-S2, AOS-019-S3; owning files/interfaces above | AOS-019-TC01, AOS-019-TC02, AOS-019-TC03, AOS-019-TC04; parameterize every condition in this clause |
| AOS-019-F03 | Network isolation must enforce the decision below application-level URL parser; no ambient browser cookies, cloud auth headers or arbitrary URL schemes. | AOS-019-S1, AOS-019-S2, AOS-019-S3; owning files/interfaces above | AOS-019-TC01, AOS-019-TC02, AOS-019-TC03, AOS-019-TC04; parameterize every condition in this clause |
| AOS-019-F04 | Results are untrusted candidates; no page text can request a new tool privilege or broaden egress. | AOS-019-S1, AOS-019-S2, AOS-019-S3; owning files/interfaces above | AOS-019-TC01, AOS-019-TC02, AOS-019-TC03, AOS-019-TC04; parameterize every condition in this clause |
| AOS-019-AC01 | SSRF fixture: 127.0.0.1, RFC1918, 169.254.169.254, DNS rebinding, IPv6 loopback, redirect to internal IP, alternative encoding blocked in resolver and sandbox. | AOS-019-S1, AOS-019-S2, AOS-019-S3; owning files/interfaces above | AOS-019-TC01, AOS-019-TC02, AOS-019-TC03, AOS-019-TC04; parameterize every condition in this clause |
| AOS-019-AC02 | Invalid content-type/oversized response safely terminated; search API failure not silently retried to a different provider. | AOS-019-S1, AOS-019-S2, AOS-019-S3; owning files/interfaces above | AOS-019-TC01, AOS-019-TC02, AOS-019-TC03, AOS-019-TC04; parameterize every condition in this clause |
| AOS-019-AC03 | SearXNG JSON 403 when not configured becomes explicit setup error; tests prove query count recorded as outbound disclosure. | AOS-019-S1, AOS-019-S2, AOS-019-S3; owning files/interfaces above | AOS-019-TC01, AOS-019-TC02, AOS-019-TC03, AOS-019-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-019-S1](../cursor/prompts/AOS-019-S1.md) | AOS-008, AOS-009, AOS-013 | Configured search adapter with quotas/query-disclosure ledger and explicit JSON/setup errors; no automatic provider choice. | AOS-019-TC01; command/report/exit, immutable evidence and diff |
| [AOS-019-S2](../cursor/prompts/AOS-019-S2.md) | AOS-019-S1 | Trusted HTTPS/IP pin/redirect/TLS/byte/deadline broker plus OS gateway policy; no ambient cookie/proxy/auth leakage. | AOS-019-TC02; command/report/exit, immutable evidence and diff |
| [AOS-019-S3](../cursor/prompts/AOS-019-S3.md) | AOS-019-S2 | Resolver/connector and actual network denial fixtures for private/mixed/encoded/DNS-rebind URLs; live search only separately scoped. | AOS-019-TC01, AOS-019-TC02, AOS-019-TC03, AOS-019-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-019-TC01 | security | `tests/integration/test_aos_019.py::test_ssrf_resolver_redirect_matrix` | IPv4/IPv6 loopback/private/metadata/encoded/mixed-address and redirect/rebind variants denied before unsafe connect. |
| AOS-019-TC02 | contract | `tests/integration/test_aos_019.py::test_pinned_tls_and_limits` | Connector uses checked IP with original SNI/Host/cert validation; scheme downgrade/bytes/decompression/deadlines fail safely. |
| AOS-019-TC03 | integration | `tests/integration/test_aos_019.py::test_search_disclosure_setup_errors` | Query is recorded as outbound even via local frontend; JSON 403/config error never silent fallback to a different paid provider. |
| AOS-019-TC04 | live | `tests/integration/test_aos_019.py::test_configured_search_gateway` | Owner-approved installed provider/gateway shows allowed public path and effective private/direct bypass denial; fake transport is not OS proof. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_019.py --junitxml=evidence/AOS-019.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

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

## Explicit web-policy preparation (2026-10-16)

Current continuation: [admitted fetch/read/retention](../design/52-ADMITTED-FETCH-READ-RETENTION.md)
connects the broker and isolated reader under task-wide source/body reservations,
current policy/lease/deadline and per-hop disclosures. See the [component guide](../testing/ADMITTED_RESEARCH_FETCH.md).
It does not issue live qualification, install search, admit semantic runners or
complete this item/G2. Search admission shares the same canonical authority checks.

[Public-web policy design](../design/37-PUBLIC-WEB-POLICY.md) adds an explicit closed
web destination to the existing versioned policy transport, with unchanged
serialized defaults and historical fingerprints. PUBLIC only, action external-send,
independent axes and owner review remain mandatory. Provider grants do not imply
web access. At63555c9,52 policy/actual disposable-Postgres checks pass; exact evidence
is in evidence/public-web-policy-2026-10-16. A privacy revision alone cannot certify
or widen a runtime; tests deliberately retain synthetic outbound denial.

Existing bounded fetch transport evidence remains in evidence/research-public-fetch-
2026-10-15. Neither that transport nor this policy declaration is an enabled search
service. Configured API/SearXNG, actual outbound query/URL disclosures, connection
grants, current-policy/lease/budget checks and enforced broker/OS integration remain
required before AOS019/G2 acceptance. No network/provider call or owner policy was
changed by this slice. Preserve the historical field name cloud_destinations for
compatibility; public-web is a separate destination within it.
