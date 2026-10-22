# Pin the model for a local Build plan or repair draft

This optional setting makes local Build proposals and finite repair drafts use an
explicit model/runtime identity. A changed engine/template/tokenizer/format cannot
silently replace the selected identity. Defaults remain unchanged. It neither
executes a Build plan nor grants approval, quality, training rights or completion.

First use [pinned local Ask](PINNED_LOCAL_MODEL_MANIFEST.md) with your existing
CPU model/cache. While **your ordinary Ask server** is running with
`pin_model_manifest: true`, save its public model identity to a new file outside
the model cache/runtime:

```bash
uv run --frozen panestria local model-manifest \
  --config /ABSOLUTE/PATH/local.json \
  --output /ABSOLUTE/PRIVATE/PATH/expected-json-model.json --json-output
```

This command reads authenticated local status and writes a fresh0600 file. It
does not generate, download, overwrite files, export chats/profile data or refresh
a qualification. `--json-output` derives a formatting expectation from the public
identity; `qualification: NOT_EVALUATED` is intentional. A raw-text expectation
cannot silently become a JSON request during dispatch.

Stop your own Ask server with Ctrl+C before running a separate local planner:
Panestria preserves existing model controllers and the foreground primary lease.
Do not stop unrelated services. Add this optional field to your existing private
[local planner settings](LOCAL_BUILD_PLANNER.md), keeping its other fields:

```json
"model_manifest_file": "/ABSOLUTE/PRIVATE/PATH/expected-json-model.json"
```

Use the existing bounded command with your already prepared contract/inventory:

```bash
uv run --frozen panestria plan propose --config /ABSOLUTE/PATH/planner.json \
  --contract /ABSOLUTE/PATH/contract.json --inventory /ABSOLUTE/PATH/inventory.json \
  --output-directory /ABSOLUTE/NEW/PRIVATE/DRAFT --local-model-run
```

The request and private journal retain the selected manifest before any model
turn. Actual startup verifies the existing cache/isolation and binds the observed
JSON runtime; a mismatch stops without a fallback inference. Success retains
`model_manifest` in `result.json`, plus the request's `model_manifest_sha256` in
`request.json`. `VALIDATED_DRAFT` still requires separate canonical stage, plan
acceptance, execution, independent final checks and exact owner merge.

The existing [finite repair workflow](LOCAL_BUILD_REPAIR.md) uses the same planner
settings. Its durable repair intent binds the complete request digest before
dispatch. An admitted failed/unknown turn remains charged to the original finite
budget. A different new-work manifest/file cannot reset that budget or rewrite a
retained result. Canonical replay keeps the original protected files/identity and
does not generate again. A fresh incompatible selection requires owner review
and supported runtime/compatibility evidence; no hot-swap is provided.

Relevant checks cover public export/no overwrite, typed proposal publication,
missing/wrong result identity, JSON/raw format separation and actual PG repair
intent/replay/budget binding. A separate actual existing-cache CPU check observes
one JSON generation after selecting the public Ask identity. It does not qualify
physical TCP, plan correctness/quality, profile keys or a release gate. See
[source-bound evidence](../../evidence/local-build-model-pins-2026-10-22/report.json).
Research query/synthesis, GPU and general replacement qualification remain open;
this component does not complete R3 acceptance or the real owner trial.
