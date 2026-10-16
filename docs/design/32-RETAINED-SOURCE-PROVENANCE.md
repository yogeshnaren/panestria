# Retained fetch/reader provenance and passage lookup

Explicit prerequisite PR #81. This trusted controller accepts only the actual
public HTTPS and isolated reader observation types after the caller has admitted
and executed retrieval. It performs no network request and grants no fetch,
policy, task, model or merge permission. Do not expose record creation to workers
or accept model JSON as an observation. Outbound admission/disclosure and the
Delegate controller remain separate required work.

SourceStore mints a fresh source ID, validates complete bounded fetch/reader
lineage and current reviewed reader program/profile/version, then retains exact
raw, text, fetch, reader and redirect bytes in the private scoped CAS. It pins
artifact metadata, commits #81's immutable record and an additional immutable
capture-proof binding/event in the same caller PostgreSQL transaction. Proof
binds source metadata, full scope and receipt/artifact hashes. Failure leaves
only inert unreferenced bytes; it cannot expose usable source IDs. Repeated
actual retrieval/re-extraction makes a new version; completed durable caller
transactions must be replayed by the workflow rather than re-fetching implicitly.

Metadata-only source records never qualify. Passage lookup requires a capture
binding plus hash/size-checked proof, raw, text, fetch, reader and every redirect
receipt. Validate closed receipt contracts, exact URLs/status/hops, normalization,
extractor/program/profile hashes, scopes and reference sets offline. Never refetch
a missing/corrupt source or silently change its version. Resolve exact half-open
UTF8 byte spans only after all checks; retain privacy and PDF layout limitations.
An exact source/passage or canonical NFC quote match yields EVIDENCE_PRESENT,
never semantic SUPPORTED. Wrong quote, fabricated ID/URL-only citation, split
UTF8, stale hash, incomplete/metadata-only/corrupt source denies.

The capture ledger records trusted controller provenance; it is not remote
hardware attestation or a claim that arbitrary host code cannot fabricate it.
The kernel/API/database are trusted, and workers have neither database
credentials nor protected-store access. Actual public TLS→isolated reader→PG/CAS
qualification is separate from injected observation/negative protocol tests.
No enabled network/API route or full release gate follows from this component.
