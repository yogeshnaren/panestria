# Deterministic retained claim evidence

Explicit prerequisite PR #82. Implement original AOS-013 claim bindings and
AOS-021 deterministic source/quote verification. SourceStore already resolves
actual retained capture proof; a real source or quote still does not entail a
claim. Semantic AOS-022 judgments remain separate and always NOT_ASSESSED here.

Closed input contains ClaimDraft plus optional exact quotes bound to its listed
passage refs, with UTF8 byte/count caps. Reject duplicate refs/quotes, unknown
fields and mismatched quote references. Models never provide canonical claim ID,
verdict or support flags. Trusted ClaimStore mints IDs, retains exact claim/quote
payload and deterministic report privately (explicit SecretStr unwrap only into
protected bytes), and stores immutable scoped artifact metadata plus only the
successfully verified source bindings. Invalid citations remain diagnostics in
the protected report and block whole-claim EVIDENCE_PRESENT. No evidence stays
NO_EVIDENCE. Draft kind is a model hint and cannot bypass support review.

Privacy inherits question/input and every verified source. Unresolved/invalid
lineage conservatively raises stored claim/report to RESTRICTED. There is no
network/model call, source repair, task promotion or API/tool exposure. Source
IDs are scoped to the exact request/task/owner/project and actual capture ledger;
byte ranges, metadata hash and normalization bind every verified passage.

Migration0026 has immutable claim/artifact pins and claim/source/capture FK-bound
passages, the existing global counter and caller-owned same-PG transaction.
Serialize a 64-claim cap per request, bound payload/report sizes, and finish all
entity writes before append_event's global lock. A read/verify operation rechecks
protected payload/report/metadata/bindings and actual current retained source
bytes offline. Later corruption returns invalid evidence, never reuses a stale
passing report or overwrites history. No full case/release promotion follows.

Actual disposable PG/CAS/reader tests cover exact NFC quote, wrong text/case/space,
missing/fabricated/metadata-only/cross-scope IDs, corrupted lineage, byte offsets,
no/partial evidence, unrelated genuine passages remaining NOT_ASSESSED, privacy,
concurrent cap, atomic rollback/event/immutability/dump restore and event-last.
Synthetic transport fixtures are labeled; actual TLS source evidence is separately
retained by #82. No new inference/search credentials or owner resources required.
