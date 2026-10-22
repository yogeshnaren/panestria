# Opt-in lossless local presentation

Structured profile Ask already supplies approved style guidance to the local
model. A separate `lossless_presentation: true` private local setting now permits
a bounded application layout pass on that model's returned text. It calls no
additional model and performs no translation, summarization, factual correction
or semantic rewrite. Those preferences remain initial generation guidance and
their quality remains unassessed.

Only the existing selected `STRUCTURED_RESPONSE_STYLE` purpose can use the pass.
The API revalidates the exact profile/ciphertext/purpose/current authority after
model return, while holding its existing transaction locks. It derives the
formatting preference from that revalidated ephemeral secret selection, formats
locally, then commits completion/observations before returning text. Withdrawal,
changed source, expired qualification, cancellation, deadline/session failure
still fence publication. The kernel also requires the structured-profile purpose
before recording a presentation observation. No new selection/grant/key exists.

The supported transform adds `- ` at each plain paragraph start. An independent
inverse must recover **every original byte**, including facts, numbers, citations,
uncertainty, punctuation and whitespace. Existing plain paragraphs can remain
unchanged. Auto format, partial output, overlarge/many-paragraph text and code,
tables, existing lists/markup, reference definitions, indentation, control or
ambiguous newline structures abstain and retain the original text. Abstention
does not assert that the original answer was correct. Output remains untrusted.

The original model usage and latency stay distinct from measured local formatting
time. Canonical request metadata retains renderer/state, UTF-8 byte lengths,
original content word/paragraph counts and mean content words per paragraph.
These are descriptive measurements, not a readability score, factual verification
or owner preference. All three remain `NOT_ASSESSED`. No preference value,
source/output text or unkeyed content/profile hash is persisted in these metrics;
the existing restricted response/hash omission remains mandatory. Original model
token counts describe generation, excluding later layout markers. Completed
request replay reads the same receipt and never generates/formats again.

Defaults and general/non-structured Ask are unchanged. This setting does not
enable the sensitive service, refresh a qualification, export private context,
train a model, select another provider or widen permission. It is a narrow S5
presentation component, not qualified semantic style rewriting, complete paired
quality/preference evidence, ModelManifest compatibility or a release gate.

Paired byte/citation/number/uncertainty fixtures and actual PG/crypto/HTTP checks
cover applied/default layouts, abstention, persisted metadata without plaintext,
one inference POST/receipt replay and real profile withdrawal after mocked local
model return. Keys/model/capacity are explicit non-live fixtures; no live model
quality is inferred from those checks.
