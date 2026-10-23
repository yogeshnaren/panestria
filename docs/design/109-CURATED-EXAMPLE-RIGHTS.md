# Separate owner-example rights and local data preparation

This is one AOS-012-S6/TC09 component. It does not change the immutable Build
archive's UNKNOWN eligibility/export DENIED, promote local reference consent,
import provider output, create a trainer or implement R6. The initial supported
lane is an explicitly classified PUBLIC owner original with separately reviewed
origin, data-rights and validation evidence. Evidence is **OWNER_ATTESTED**;
software verifies binding/current consent, not authorship, law or factual truth.

## Contracts and authority

CuratedExample closes the input schema, limits input/response to1024/2048 UTF-8
bytes and defaults origin UNKNOWN. OwnerEvidence closes each separately PUBLIC
role-bound document with exact canonical example subject hash, assessment,
nonblank basis and original validity timestamp. All three ORIGIN/DATA_RIGHTS/
VALIDATION roles are needed. Positive evidence additionally states no provider or
model input, the local training-data-preparation purpose, and owner validation.
ALLOWED flags alone are insufficient. Unknown/missing/expired evidence stays
UNKNOWN; provider/local-model output is DENIED in this lane regardless of flags.
No provider agreement or output-ownership permission is inferred.

Prepare reads private files once and writes nothing. Its canonical review hash
binds typed example/evidence content, owner/project, current policy, purpose and
1–30-day eligibility period (default7). It returns the example subject hash for
preparing evidence. Record reconstructs that exact review and requires separate
owner-review and, for ALLOWED, training-data-purpose flags. Current PUBLIC/local
read and edit must both PERMIT. Existing policies are never widened. Source
reference or subscription work retention is not this consent.

Migration0039 adds immutable scoped review and withdrawal facts to the same
Postgres database, with existing global task_event sequence allocation. No task
state, scheduler or second authority database is added. Project policy share
locks precede a nonblocking-bounded project registry advisory lock; serialized
rights writes, export admission and withdrawals use that same lock. The exact
preview, eligibility, consent, actor and expiry commit in one transaction.
Replay returns the original expiry/sequence and never becomes a newer decision.
Latest different reviews supersede older ones; old-receipt replay cannot undo a
later denial. Expired replay is historical/current false. The original latest
owner decision is distinguished from observed current eligibility in inspection.

Content identity excludes the declared origin, so a previously recorded provider/
model origin for the **same exact input/output in this project** cannot be erased
by changing the origin flag. UNKNOWN history is not fabricated non-owner proof;
new explicit owner evidence can resolve it. Withdrawal is permanent for that
same content in this project, needs an existing scoped review and no current
read/edit permit, and preserves all history. This is not a detector of copied or
near-duplicate content, cross-project provenance or false human attestations.

## Export, recovery and storage

An explicit export selects at most16 unique current reviews. It revalidates
policy, latest decision, consent/evidence expiry and withdrawal under the same
locks before writing one new private local JSON file. Unknown/denied/stale data
cannot produce an empty successful export. Exact duplicate or conflicting inputs
are refused. A deterministic hash of exact UTF-8 input assigns development or
holdout independently of response/metadata; the same input stays in one fold.
Semantic/near-duplicate detection and real training/holdout qualification remain
separate future work; this packet cannot promote a model.

The packet preserves typed example bytes, review/example and canonical evidence
hashes, fold and original expiry. It is at most128KiB and contains no executable
trainer, credentials or automatic external destination. The caller selects an
existing private directory; output is exclusive mode0600 and never overwrites.
A partial I/O failure remains UNAVAILABLE and may leave a partial file; inspect
it or choose a new explicit path, without cleanup/retry authority. Copying the
packet changes no canonical decision. validate-export rechecks every entry
against current scoped PG records, so file restore alone cannot revive withdrawn,
expired, superseded or old-policy permission. Full DB restore is an operator
recovery decision, not a fresh rights approval. Preserve current decision/withdrawal
history with data backups. No app import silently re-adopts an old approval.

Inspect is a repeatable-read read-only metadata observation, not another consent
or export permission. It reports original/observed eligibility, current revision,
policy/expiry/withdrawal and observation time without example or basis text.
After lost record/output responses, inspect canonical state and validate an
existing packet before another explicit intent. Export has no model/paid action;
new-file exclusivity prevents overwriting a prior result.

Registry writes refuse at4096 reviews or a conservative8MiB JSON-preview payload
budget per owner/project under the registry lock. This is not a physical Postgres,
index/WAL/backup footprint ceiling. Each explicit output is bounded; the app does
not manage an arbitrary owner-chosen export directory's aggregate growth. Nothing
is automatically deleted on expiry/withdrawal, including already exported files.
The eligibility period controls future app admission, not storage retention.

The migration updates both observed schema fingerprints and local startup's exact
head pin. Empty downgrade/upgrade is tested; populated audit downgrade refuses
instead of deleting decisions. Owner review databases/services were not migrated.
Historical specs, certificates and observations keep their source identities.

[Owner guide](../testing/CURATED_EXAMPLES.md) and
[source-bound observations](../../evidence/curated-example-rights-2026-10-23/report.json)
retain real disposable PG/CLI/files with synthetic evidence/policy fixtures,
original stale-snapshot failure and correction, and one detected withdrawal-guard
mutation. These do not establish legal/semantic verification, actual training,
provider-output eligibility, full S6/TC08/TC09/G3 or owner trial acceptance.
