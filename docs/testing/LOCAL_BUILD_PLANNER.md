# Draft a Build plan with the existing local model

This command turns an explicit goal and worker inventory into a reviewable plan.
It runs locally and produces files. It does not generate project code or launch
Claude, connect to the database, accept its own plan or approve a merge.

Use a private checkout with frozen dependencies, Docker/the existing pinned image
and the already provisioned dedicated local model cache. No model is downloaded.
The initial model is `qwen2.5:1.5b-instruct`, pinned by its existing digest. Keep
at least the configured foreground CPU/RAM/disk/power reserves. If another owner
model service is present, this command refuses and preserves it; it does not stop
that service or silently use a different provider.

Create an owner-only0600 JSON configuration outside Git. Replace each path/UUID
with your existing setup's values:

```json
{
  "schema_version": 1,
  "owner_id": "OWNER_UUID",
  "project_id": "PROJECT_UUID",
  "model_cache": "/absolute/existing/dedicated/models",
  "runtime_directory": "/absolute/private/planner-runtime"
}
```

Cache and runtime must be separate absolute paths without symlink aliases. The
cache contains only `blobs` and `manifests`. Existing runtime directories must be
owner-private. Use a new private output directory for every deliberate attempt;
its parent must already exist. Output, runtime and cache cannot overlap.

Prepare a valid owner-authored goal contract and inventory using
[Build preflight](BUILD_PLAN_PREFLIGHT.md) or the
[actual native inventory command](NATIVE_PLAN_EXECUTION.md). Owner/project IDs
must match the configuration. The complete contract/checks/non-goals must fit
the bounded model context; oversized inputs are refused without dropping checks.
Use zero API cash, declared editing workers and a `trusted-integrator` with
`trusted-test-runner` capability also permitted by the goal.

```bash
uv run --frozen panestria plan propose \
  --config /absolute/private/planner.json \
  --contract /absolute/private/contract.json \
  --inventory /absolute/private/inventory.json \
  --output-directory /absolute/private/draft-1 \
  --local-model-run
```

Expect `VALIDATED_DRAFT`, `authority: PROPOSAL_ONLY`, exact hashes, model identity,
measured generation latency/usage and `execution_authority: NONE`. Review
`proposal.json`, `validation.json` and `result.json` in an editor. The model
proposes editing assignments. Panestria adds the final node with every goal check
and all editing paths, reserving its wall budget before generation. The complete
graph must fit the original scope/capabilities/checks/retry/time/cash constraints.
Review whether the decomposition actually solves the intent; structural validation
is not a quality judgment or proof of working project code.

The directory also retains frozen `contract.json`, `inventory.json`, private
`request.json` and, for a complete response, `response.txt`. These can contain
restricted goal/model data and stay outside Git. A rejected/incomplete call exits1
with UNAVAILABLE and retains its journal. An interrupted run may remain STARTED;
do not assume completion. Repeating the same output directory never invokes the
model again. There is no automatic repair, retry, source edit or provider switch.

Only after review, stage the frozen files and separately accept the exact consent:

```bash
panestria plan stage OWNER_UUID PROJECT_UUID --contract /absolute/private/draft-1/contract.json --proposal /absolute/private/draft-1/proposal.json --inventory /absolute/private/draft-1/inventory.json --idempotency-key reviewed-draft-1
panestria plan inspect OWNER_UUID PROJECT_UUID PLAN_UUID --output /absolute/private/canonical-review.json
panestria plan accept OWNER_UUID PROJECT_UUID PLAN_UUID EFFECT_SHA --accept-plan
```

`plan stage` requires the separately configured database/current policy and PUBLIC
zero-cash contract. The offline planner can draft other canonical classifications;
this does not make them eligible for the PUBLIC native executor. The current
[native execution path](NATIVE_PLAN_EXECUTION.md) additionally requires exactly
two independent Claude edits followed by the final integrator and an actual
matching runtime certificate. A draft containing another shape is not silently
reshaped into an executable plan. General DAG/second-adapter work remains pending.

[Observed results](../../evidence/local-build-planner-2026-10-20/report.json)
include actual private-file CLI/graph/receipt checks and an actual local CPU draft.
On clean `256be15`, the corrected local model produced a valid assignment and the
trusted compiler produced the final graph in19.63seconds end to end (17.46seconds
reported generation,560input/95output tokens). Original failed graph output is
preserved separately. These are synthetic examples with declaration fixtures,
not a general planning-quality benchmark, certified worker inventory or G3 pass.
