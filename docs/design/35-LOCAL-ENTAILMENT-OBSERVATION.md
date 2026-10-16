# Actual offline entailment observation

Explicit prerequisite PR #84. Evaluate the pinned public SNLI preflight through
existing LocalProvider and the existing read-only model cache, never download a
model or use a cloud/provider fallback. Runtime qualification uses
ModelRuntime(gpu=False,preserve_existing=True): preserve every existing model
service, use actual nonroot/read-only/network-none Docker, private Unix socket,
CPU2/RAM2.5GiB and exact model digest. No owner service is stopped or replaced.

The probe accepts only the immutable public corpus pin. Its input projection
contains no gold labels. A fixed rubric/prompt, known model ref and bounded
sequential calls produce a closed verdict or explicit UNKNOWN for invalid or
truncated output. Provider unavailability/deadline/cancellation stops the batch;
uncalled cases are not invented as completed model abstentions. A partial batch
has no complete-fold score. No retry/tuning on qualification labels or provider
switch. Keep actual prompt hashes, output hashes (no reasoning text), bounded
observed usage/timing, model/runtime manifest and per-case parsing reasons.

Both folds have separate actual observations. Report confusion/coverage/precision
with the corpus's domain/artifact/contamination/small-sample limits. These metrics
alone do not authorize semantic support, certify model-family independence or
promote any release. A poor/unavailable local verifier must remain UNKNOWN or
abstain in production; never fabricate calibration. No profile/private data,
credentials, training or actual paid/API inference is needed.
