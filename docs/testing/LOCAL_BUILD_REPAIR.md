# Draft a local repair from stopped Build work

`plan propose-repair` connects an existing stopped PUBLIC Build to the existing
local planner. It drafts editing assignments from the original contract and
recorded task/check failures, with the **remaining cumulative wall envelope**.
It does not write project code, repair a source tree itself, stage/accept a new
version, dispatch a worker, release a claim or approve a merge. Structural
validation is not repair-quality qualification.

Use the existing private [Build configuration](OWNER_BUILD_CLI.md), migrated (through `0037_repair_draft_intents`)
`PANESTRIA_DATABASE_URL` environment and [local planner settings/cache](LOCAL_BUILD_PLANNER.md).
Owner/project IDs must match. No credentials, model download, provider switch or
new database/service is configured by this command. The local model uses its
existing CPU resource admission and isolated owned runtime, preserving owner
services. Each deliberate proposal uses one offline generation request, at most60 seconds
and1024 output tokens, with no automatic retry. Before model I/O, an acknowledged
Postgres intent reserves **360 seconds** for generation and lifecycle overhead
against the original goal envelope. All worker versions and model reservations
remain charged, including rejected/unknown attempts. The360-second reservation is
conservative capacity accounting, not measured latency or an OS interruption
guarantee; late returns cannot publish or authorize another turn. This is not an
autonomous repair loop. Back up and forward-migrate an intended database through
the normal owner setup process; this change does not migrate a running owner
database. Downgrade refuses to remove the guards once repair I/O audit exists.

First inspect the stopped plan, source-bound checks and original failure. Release
only physically confirmed attempts using [receipt-bound release](RETURNED_BUILD_RELEASE.md).
An UNKNOWN/claimed process, held slot, unconfirmed evidence or uncertain merge
must be reconciled; a timeout or this planner cannot free it. Keep the exact latest
accepted plan UUID/proposal SHA and its returned-release proof SHA.

```bash
uv run --frozen panestria plan propose-repair \
  PARENT_PLAN_UUID PARENT_PROPOSAL_SHA256 RETURN_PROOF_SHA256 \
  --build-config /absolute/private/build.json \
  --model-config /absolute/private/planner.json \
  --output-directory /absolute/private/repair-draft-1 \
  --maximum-versions 3 --local-model-run \
  --idempotency-key repair-1
```

The output directory must be new, private and separate from the cache/runtime;
its parent already exists. Expect VALIDATED_DRAFT, PROPOSAL_ONLY,
`canonical_plan_state: NOT_STAGED`, `execution_authority: NONE` and exact context,
proposal and model usage/latency receipts. Review `repair-context.json`, the
original contract/inventory, private request/response, compiled proposal and
validation. The compact prompt carries stopped task states/check verdicts, not
raw worker logs or arbitrary tool commands. Full source bindings remain in the
private context/journal. The trusted compiler preserves original scope/checks,
reserves final integration time and rejects output exceeding remaining time.

The controller rereads canonical policy/plan/tasks/evidence before publication.
Changed goal events, state, budget, parent or authority refuse publication and
retain the private failure journal/response without a proposal. Oversized context
refuses without silently dropping checks. Never use a failed/interrupted run as
an accepted repair or relabel it as a new source. Reusing its directory cannot
invoke the model again. An explicit idempotency key is optional; the default is
the exact absolute output-directory identity. The same key/parent/proof/limit/path
replays only the original protected bytes, marked HISTORICAL_NO_AUTHORITY, without
a model call. Changed/missing bytes or changed bindings refuse replay. Preserve
the original directory; a completed receipt does not acquire new authority.

The first acknowledged intent fixes at most `maximum_versions - 1` model turns
(one or two) for this goal. A fresh key, directory, process or plan version cannot
reset that cap or its wall reservations. A new deliberate turn needs its own
fresh directory, remaining turn/budget capacity and all current checks. If a model
return or outcome acknowledgment is uncertain, the intent stays UNCONFIRMED; new
model calls and canonical revisions stop. There is no automatic retry or
force-clear command. Do not delete an intent or claim a timeout proved return.
Inspect the original model/runtime evidence for actual reconciliation.

```bash
panestria plan repair-turns GOAL_UUID --config /absolute/private/build.json
```

This read-only command shows turn IDs, outcomes, reservations and receipt hashes.
`plan progress` exports the same counters, and the Build terminal shows reserved
planning seconds and unknown turns. It grants no retry or release authority.

Review the decomposition and failure diagnosis as owner. Then use the **revision**
command (not initial `plan stage`) with the frozen files:

```bash
panestria plan revise OWNER_UUID PROJECT_UUID PARENT_PLAN_UUID PARENT_PROPOSAL_SHA256 RETURN_PROOF_SHA256 --proposal /absolute/private/repair-draft-1/proposal.json --inventory /absolute/private/repair-draft-1/inventory.json --maximum-versions 3
panestria plan inspect OWNER_UUID PROJECT_UUID NEW_PLAN_UUID --output /absolute/private/repair-review.json
panestria plan accept OWNER_UUID PROJECT_UUID NEW_PLAN_UUID NEW_EFFECT_DIGEST --accept-plan
```

Canonical [revision authority](BOUNDED_PLAN_REVISIONS.md) independently rechecks
the parent, proof, all prior envelopes, finite version limit, current policy and
physical work. A local draft grants none of these. Only then use the explicit
supported native run, current runtime certificate and separate final owner merge.
Old failed evidence stays historical. Changing scope/privacy/cost requires new
corresponding authorization, not an edited JSON or a model suggestion.

STOPPED reasons identify held/unknown work, missing return proof, superseded
parent, exhausted wall/version budget or repeated unchanged failure. Two equal
protected failed-candidate fingerprints across the family stop this local repair
path **before another model call** and require owner review. This does not widen
or silently override the existing explicitly reviewed manual revision path.

[Connected evidence](../../evidence/local-build-repair-2026-10-21/report.json)
includes actual CLI/PG/Git/MCP/Docker, failed-run release, model draft, separate
revision consent/execution and exact final protected merge. Models/native/auth
are explicit nonlive fixtures. Budget rejection, changed-source suppression and
repeated failed-tree stopping are also observed. This does not qualify real
repair accuracy, general DAG/native compatibility, persistent automatic repair,
full AOS-025, G3 or owner acceptance.

[Durable intent evidence](../../evidence/repair-draft-intents-2026-10-21/report.json)
adds concurrent admission, byte-bound replay, lost acknowledgment and actual
backup/restore observations. See [the accounting design](../design/77-DURABLE-REPAIR-INTENTS.md).
The earlier report remains bound to its original per-command implementation.
