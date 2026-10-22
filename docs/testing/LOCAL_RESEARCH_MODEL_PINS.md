# Pin the model used for local research drafts

Local query proposals and synthesis drafts can now retain an exact public
model/runtime identity. This does not verify their answers or authorize web access.
The setting is optional; existing unbound behavior remains unchanged.

Use the [existing model-identity export](LOCAL_BUILD_MODEL_PINS.md) from your
running pinned ordinary Ask service:

```bash
uv run --frozen panestria local model-manifest --config /ABSOLUTE/PATH/local.json \
  --output /ABSOLUTE/PRIVATE/PATH/expected-json-model.json --json-output
```

It writes a fresh0600 public metadata file, starts no inference and refreshes no
qualification. Stop only your own Ask server before starting another local model
controller. Add the following optional field to your existing private local
query/synthesis settings, preserving its owner/project, private retained root,
cache and runtime fields:

```json
"model_manifest_file": "/ABSOLUTE/PRIVATE/PATH/expected-json-model.json"
```

Then use the existing [query proposal](LOCAL_RESEARCH_QUERY_PLAN.md) or
[synthesis workflow](LOCAL_RESEARCH_SYNTHESIS.md). Query proposals need a staged
PUBLIC question and grant no web authority. Synthesis needs existing valid
retained passages and a VERIFYING request. Actual search setup remains deferred;
this component does not configure it or create source evidence manually.

Before a genuinely new model turn, Panestria snapshots the selected JSON identity
and commits it with the original request hash in the durable STARTED event.
Startup/provider/returned identity must match before an output is retained.
Missing/wrong identity stops; there is no fallback or automatic retry. Current
policy, task, source, cancellation and original publication checks still run.

Successful private JSON inspection/export now includes the original
`model_manifest`. It is checked against the original immutable intent, not today's
configuration. Inspection and canonical replay do not open today's selection file:
old drafts remain readable if it changes or becomes unavailable. Replaying the
same key performs no additional generation. Historical unbound artifacts omit the
new field, preserving their original canonical bytes and hashes.

The manifest describes model/runtime/container-tokenizer/template/capability
identity; it grants no accuracy, private-context sharing or training rights.
Query quality and synthesis semantic support stay **NOT_ASSESSED**. A cited draft
has no task completion authority. General model replacement, GPU support, full
original gates and the real owner trial remain separate.

[Recorded checks](../../evidence/research-model-pins-2026-10-22/report.json) include
26 connected cases with actual PostgreSQL/CAS/isolated reader and explicit model/
HTTPS fixtures. A separate actual cached CPU synthesis run retained a typed cited
draft, its selected identity and one-call replay/owned cleanup. Its request state
and HTTPS observations were synthetic; it is not actual search, factual support,
physical TCP, profile-key or release qualification. Original source and measured
token/controller timing observations remain in the evidence report.
