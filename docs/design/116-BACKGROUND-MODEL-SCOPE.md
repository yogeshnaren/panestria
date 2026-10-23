# Model-scoped background intent and runs

Revision3 MVP-X11 requires preferred-model work with independent account/model
quota windows. This completes the queue/controller connection to
[reviewed native model selection](115-REVIEWED-NATIVE-MODELS.md). It does not
enable an owner's queue, qualify a model or renew billing/usage evidence.

Legacy policy schema1 retains `model_ref: null` and original canonical hashes.
Legacy run schema1 retains an absent model field and original hashes. Original
source `8b6aef8eff15a93784bdcd0fe2f4099f072b2c82` serialization fixtures verify
both forms; no historical record is upgraded or rewritten.

Policy schema2 requires an exact closed native model ID, at least one account-wide
window and one exact-model window. Every window uses the same account/provider;
another model or a floating alias refuses. The finite run records that model in
schema2 and validates it against its original immutable binding on reconstruction.
Controller settings must match before start and each claim, and throughout worker
authority/refresh/monitoring/tools/final integration. The separately reviewed
native connection, model-specific certificate/inventory, original account link,
policy/lease/claim/effect/approval rules still intersect that authority.

The existing quota service evaluates every exact scope independently; a model
reserve/exhaustion cannot disappear into an available account window. Returned
observations now expose model scope and requested model separately from UNKNOWN
actual model identity. No family-to-version quota mapping, pooled quantity,
percent-to-token conversion, savings claim or credit authorization is invented.
Bounded explicitly authorized unknown best effort remains possible under existing
rules. The shared foreground reserve, serial background worker, original wall
budget, freshness, withdrawal, ambiguous-effect reconciliation and observed-limit
fences are unchanged. No fallback or automatic retry is added. The read-only selector filters to the
configured model before priority/reset ordering, so an unmatched higher-priority
item neither changes routing nor starves eligible matching work.

`background draft` derives only a review request from private settings: schema2,
exact model, account session/weekly windows plus `selected-model`. Billing stays
UNKNOWN and unknown-quota best effort stays false. Existing exact preview/hash/
enqueue and account review remain separate. The synthetic connected journey uses
actual PG/Git/MCP/Docker, scripted native/auth/account/certificates and synthetic
fresh disabled-usage billing. Owner reality remains stale/background OFF.

This task follows PR205 and starts from its explicit prerequisite branch, fetched
against current main. After205's verified merge, current main was merged into
this task without rewriting its commits. New CI/review is required on this exact
task. Required provider/model/host quality and cumulative original cases remain
open; this component issues no runtime certificate or release pass.
