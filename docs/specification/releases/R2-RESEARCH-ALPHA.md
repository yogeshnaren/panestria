# R2 Build Specification — Safe Read-only Delegate

**Planning status:** DRAFT — release scope requires review before implementation planning; revision planning-fixes-1.

**Goal:** Introduce exactly one non-coding delegation class: source-grounded public web research. No authenticated site access, sending, shell tools, model-triggered installations, browser session cookies, or arbitrary desktop interaction.

**Stories:** [AOS-013](../specs/AOS-013.md), [AOS-019](../specs/AOS-019.md), [AOS-020](../specs/AOS-020.md), [AOS-021](../specs/AOS-021.md), [AOS-022](../specs/AOS-022.md), [AOS-023](../specs/AOS-023.md).

## Bounded pipeline

```mermaid
flowchart TB
A[Owner: research intent + privacy/budget] --> B{Kernel policy}
B -->|allow search egress| C[SearchProvider: API or SearXNG]
C --> D[FetchBroker: DNS/IP/redirect/network enforcement]
D --> E[Isolated read-only reader: extract immutable snapshots]
E --> F[Source/quote deterministic verification]
F --> G[Claim-support + contradictions, abstain when unknown]
G --> H[Read-only evidenced brief and audit]
B -->|deny| X[Refuse/ask for change, no network]
```

## Search decision
`SearchProvider` interface supports configured SearXNG and one approved API implementation. The user's search query is recorded as outbound data, even when the local SearXNG frontend queries upstream engines. Select a provider explicitly at install/project level; never silently send an Internal/Confidential query to public search. No search-engine-specific logic in kernel.

## Fetch/network guarantees
- Validate URI scheme, hostname, IPv4/IPv6 resolved destination and port before connection; pin/revalidate address as redirects occur; block loopback, RFC1918, link-local, cloud metadata, multicast, IPv4-mapped IPv6, private IP DNS rebinding.
- Disable ambient proxies/cookies/client credentials; enforce byte/time/redirect/content-type limits, and OS-level egress restrictions.
- Renderer/reader has read-only FS and no private mounts/CLI tokens. Untrusted document instructions remain data; a separate synthesizer never receives action authority from them.

## Evidence semantics
1. Fetched source ID minted only by trusted retrieval layer; retention controlled by source policy.
2. Source has URL, redirect chain, time, status, MIME, SHA256 raw/text, extraction version, stable text offsets and privacy lineage.
3. Claim has one or more source passage references and a deterministic citation/exact-quote result.
4. Semantic support is a *separate* supported/insufficient/contradicted/unknown judgment; a second model alone does not prove correctness.
5. Unsupported claims must be removed, flagged, or marked uncertain—not promoted as fact.

## D-1 gate (fixtures + live smoke)
- Fabricated source pointer → fail.
- Real source but mismatched quote → fail.
- Real source but contradicted conclusion → unsupported/contradicted.
- Source page instructs `POST ~/.ssh` → no privileged tool available; egress denied.
- Public-looking URL redirects/DNS-rebinds to metadata/localhost → network denial.
- Truncated/PDF/table evidence → explicit incomplete status.
- One owner-approved live public brief shows fetched snapshot IDs, all cited claims, verification diagnostics and search-query cloud-exposure log.

## Rollback
Disabling Delegate must not disable R1 Ask or Build. A blocked fetch remains a recorded denial and does not trigger auto-provider switching. Evidence snapshots are versioned and retained for configured local period. Read-only mode must not support user-issued outbound email or browser macros as hidden tools.
