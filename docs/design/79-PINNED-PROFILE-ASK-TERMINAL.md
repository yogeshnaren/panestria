# Pinned profile Ask terminal

AOS-017-S4 and MVP-X07/X08 need an explicit terminal selection over the existing
restricted profile Ask contract. Reuse the keyboard Ask view and cancellation/
receipt API; do not implement another inference or profile state store.

A private immutable-in-session selection names the exact profile row, approved
fields, purpose and offline destination. Scoped canonical metadata plus the new
GET `/v2/ask/status` confirm configuration before question disclosure. Status
reads no key/profile or model and does not qualify readiness; all actual current
source/policy/key/resource/model admission remains in the existing POST `/v2/ask`.
No default sensitive-mode mounting, credential or key provisioning is added.

Client replies must match the selected metadata and restricted/offline omitted-
response-fingerprint mode. A private answer may appear only from its immediate
confirmed POST response; GET receipts remain content-free and cannot reconstruct
it. No ordinary Ask/provider fallback or automatic profile-version upgrade is
allowed. HTTP has a65-second Ask envelope and5-second controls; the existing
model generation30-second deadline is unchanged.

A potentially committed POST keeps its request identity through transient receipt
failures. Authentication/scope loss clears sensitive views. Explicit refresh can
observe completion without another model call or reconstructing the unretained
answer. A canonical UNAVAILABLE outcome joins existing terminal states in the
shared Ask client/view; this allows honest resource-denial inspection without
assuming a failed transport proved the request never existed. No automatic new
request, retry, release or authority follows that observation.

[Source-bound observations](../../evidence/profile-ask-terminal-2026-10-21/report.json)
cover actual PG/crypto/HTTP/PTY with synthetic keys/model/capacity, ordinary Ask
regressions, wrong receipt fingerprint/source refusal, cancellation and lost
reply recovery. The default goal-only OpenAPI snapshot is unchanged because it
does not mount optional Ask routes. Supported qualified personal-mode service
onboarding, actual key/model conformance, private examples and paired presentation
quality remain required; this client does not complete original S4/S5/S6/gates.
