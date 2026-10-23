# Review and save owner-authored examples for later local data preparation

This workflow prepares data for a possible later project. It starts no training,
model, API, search, background job or memory promotion. Build archives keep their
original UNKNOWN training eligibility/export DENIED. This first lane accepts
only PUBLIC owner originals with no provider/model inputs. It cannot turn a
Claude answer, subscription entitlement or local-reference note into training
permission. The application records explicit owner attestations; it does not
verify copyright, agreements, authorship or semantic truth automatically.

Use updated `main` with the existing Python environment and private database
credential. The selected migrated owner/project must already permit PUBLIC local
read **and edit**. The curator creates no project and changes no policy. It needs
no native login, runtime certificate, model cache or new credential.

Migration0039 adds canonical immutable rights/withdrawal records. Deliberately
back up and migrate the selected database using the normal owner process before
using this feature; this task did not migrate your running review database:

```bash
uv run --offline --frozen alembic -c migrations/alembic.ini upgrade head
```

A database containing rights records refuses downgrade to avoid destroying its
audit. Use reviewed forward repair or the normal operator restore process. The
new exact startup head/fingerprints describe the new schema; original historical
certificates do not become current qualifications.

## Prepare a candidate and three separate evidence documents

Choose a new owner-only working directory (mode0700). Create mode0600 files for
scope and data. `scope.json` contains metadata only, using your existing IDs:

```json
{"schema_version":1,"owner_id":"OWNER_UUID","project_id":"PROJECT_UUID"}
```

An original synthetic practice `example.json` can contain:

```json
{
  "schema_version": 1,
  "origin": "OWNER_AUTHORED",
  "privacy_class": "PUBLIC",
  "input": "How many sides does a triangle have?",
  "response": "Three."
}
```

Use your own accurately classified material for actual work. Unknown/private data
is not supported by this PUBLIC-only lane. Never add credentials or real private
material to these example documents or Git.

```bash
panestria examples prepare --config /absolute/private/scope.json \
  /absolute/private/example.json
```

Expect REVIEW_ONLY and proposed eligibility UNKNOWN without the separate evidence.
Copy the returned `example_sha256` as each evidence document's `subject_sha256`.
The separate `review_sha256` identifies the whole proposed review, not the example.

Create three files from this template, one per role. Keep UNKNOWN until you have
personally checked the relevant basis. These templates are **not actual rights
proof** and must not be automatically filled as ALLOWED for your real material:

```json
{
  "schema_version": 1,
  "privacy_class": "PUBLIC",
  "role": "ORIGIN",
  "subject_sha256": "EXACT_EXAMPLE_SHA256",
  "assessment": "UNKNOWN",
  "basis": "Describe the actual evidence and limitations you personally checked.",
  "valid_until": "JUSTIFIED_FUTURE_ISO8601_TIME_WITH_TIMEZONE",
  "assessment_source": "OWNER_ATTESTED",
  "provider_basis": null,
  "permitted_purpose": null,
  "validation_method": null
}
```

| File/role | Independent decision needed before ALLOWED |
| --- | --- |
| `origin.json` / ORIGIN | Check provenance and explain it; `provider_basis` must explicitly be `NO_PROVIDER_OR_MODEL_INPUTS`. Provider/model output stays denied in this lane. |
| `rights.json` / DATA_RIGHTS | Explain actual rights for the selected original and purpose; `permitted_purpose` must be `LOCAL_TRAINING_DATA_PREPARATION`. Ownership of a subscription/output is not this evidence. |
| `validation.json` / VALIDATION | Check the specific input/response against appropriate references and describe limitations; `validation_method` must be `OWNER_REVIEWED`. A model saying it is correct is insufficient. |

Every document needs its own PUBLIC classification, role, exact subject hash,
assessment, nonblank basis and valid-until time. A missing role/basis stays UNKNOWN;
any explicit denial stays DENIED. If facts are unresolved, retain that status.
Previously recorded model provenance for the same exact content in this project
cannot be cleared just by relabeling it owner-authored. Unknown origin can be
resolved only through a fresh exact owner review with the separate evidence.

## Review, separately consent, and inspect

```bash
panestria examples prepare --config /absolute/private/scope.json \
  /absolute/private/example.json --evidence /absolute/private/origin.json \
  --evidence /absolute/private/rights.json --evidence /absolute/private/validation.json
```

Read the **entire exact preview**, including text, scope, role evidence, purpose,
policy and eligibility period. Proposed ALLOWED still exports nothing. Then,
only if the statements and purpose are correct, use that returned review hash:

```bash
panestria examples record --config /absolute/private/scope.json \
  /absolute/private/example.json EXACT_REVIEW_SHA256 \
  --evidence /absolute/private/origin.json --evidence /absolute/private/rights.json \
  --evidence /absolute/private/validation.json \
  --confirm-owner-review --accept-training-data-purpose
panestria examples inspect --config /absolute/private/scope.json EXACT_REVIEW_SHA256
```

Expect OWNER_REVIEW_RECORDED, original `expires_at`, current/historical status and
OWNER_ATTESTED assessment. ALLOWED requires both flags; ordinary reference/owner
review alone grants no training-data purpose. UNKNOWN/DENIED judgments can be
recorded with `--confirm-owner-review` alone and cannot export. The default
eligibility period is7 days, capped by original evidence validity. To choose
1–30 days, use the same `--days DAYS` on prepare and record. This does not delete
storage when it expires.

Exact replay preserves original expiry/sequence, and replay of an older decision
cannot undo a newer denial. Expired replay is historical/current false. Changed
files, role, policy or period require a new exact preview. After an interrupted or
lost response, `inspect` observes canonical metadata without repeating a decision.
Its snapshot is not authority to export; the next export checks everything again.

## Export and validate a copied/restored packet

Choose a new file in an existing mode0700 directory:

```bash
panestria examples export --config /absolute/private/scope.json \
  --review EXACT_REVIEW_SHA256 /absolute/private/prepared-examples.json
panestria examples validate-export --config /absolute/private/scope.json \
  /absolute/private/prepared-examples.json
```

Repeat `--review` for up to16 selected current examples. Expect SAVED, a packet
SHA256, example count and `training_started: false`. The private JSON contains
examples, original review/evidence hashes, expiry and development/holdout folds.
Duplicate/conflicting exact inputs are refused. The same input bytes always
stay in one deterministic fold; this is not semantic/near-duplicate detection or
a qualified training corpus. Actual training/promotion requires the separately
authorized later phase.

`validate-export` checks data/lineage against current scoped database decisions.
A copied file can validate while its original decisions remain current; changing
its content/fold, an expired/superseded review, policy change or withdrawal refuses.
File possession or restoring an old file grants no authority. Preserve current
canonical rights/withdrawal history with backups; a full database rollback is an
operator recovery decision, not new consent. This component imports no old packet
as an active decision automatically.

## Withdraw and understand storage

```bash
panestria examples withdraw --config /absolute/private/scope.json \
  EXACT_REVIEW_SHA256 --confirm-withdrawal
```

Expect WITHDRAWN and `history_deleted: false`. Withdrawal for the same content in
this project is permanent in this first lane; it remains possible after policy
revocation/expiry. The app stops future export/validation and does not erase
history or already exported files. Inspect actual canonical state rather than
replaying old approval. No other project is implicitly granted access.

Each packet is at most128KiB, written once as mode0600 without overwriting. Registry
writes refuse at4096 reviews or a conservative8MiB JSON-preview payload budget per
project; physical DB/index/WAL/backups can use more. Explicit output files have no
automatic aggregate pruning. Storage/capture failures return UNAVAILABLE and may
leave a bounded partial output, never a successful receipt; inspect or select a
new deliberate filename. No automatic retries, deletion, provider fallback or
credential changes occur. Keep these files/metadata private.

[Source-bound evidence](../../evidence/curated-example-rights-2026-10-23/report.json)
uses actual disposable PG/CLI/files with synthetic owner attestations and policy
fixtures. It preserves the original stale-schema-snapshot failure/correction and
one detected withdrawal-guard mutation. It is not legal verification, a qualified
model/training run, provider-output eligibility or full S6/TC08/TC09/G3 acceptance.
