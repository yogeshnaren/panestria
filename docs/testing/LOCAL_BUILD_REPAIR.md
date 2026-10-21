# Draft a local repair from stopped Build work

`plan propose-repair` connects an existing stopped PUBLIC Build to the existing
local planner. It drafts editing assignments from the original contract and
recorded task/check failures, with the **remaining cumulative wall envelope**.
It does not write project code, repair a source tree itself, stage/accept a new
version, dispatch a worker, release a claim or approve a merge. Structural
validation is not repair-quality qualification.

Use the existing private [Build configuration](OWNER_BUILD_CLI.md), migrated
`PANESTRIA_DATABASE_URL` environment and [local planner settings/cache](LOCAL_BUILD_PLANNER.md).
Owner/project IDs must match. No credentials, model download, provider switch or
new database/service is configured by this command. The local model uses its
existing CPU resource admission and isolated owned runtime, preserving owner
services. Each deliberate proposal is one offline call, at most60 seconds and
1024 output tokens, with no automatic retry. Its model run has the same explicit
local-planner intent as an initial draft; worker versions still charge their full
original cumulative envelopes. This is not a persistent autonomous repair loop.

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
  --maximum-versions 3 --local-model-run
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
invoke the model again; another deliberate attempt needs a fresh directory and
all current checks. No automatic alternative model or retry is attempted.

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
