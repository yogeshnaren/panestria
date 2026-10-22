# Inspect the model used by local Ask

This optional R3 component saves the exact public model/runtime description with
each prepared Ask context. A different model name, runtime identity or incompatible
context cannot silently replace it. Application-owned memory stays in PostgreSQL;
no embeddings, KV cache or private profile is copied into a model manifest.

Start with the existing [offline Ask setup](LOCAL_ASK_SETUP.md), its already
migrated database and existing dedicated model cache. This component installs or
downloads nothing. It currently supports the CPU/raw-text local launcher; the
JSON research/planner and GPU paths retain their existing binding behavior.

Add one field to **your existing private local Ask JSON file**, preserving all
other fields and its private permissions:

```json
"pin_model_manifest": true
```

Restart your own local Ask server when convenient. Do not start a second server
on an occupied port or stop an unrelated model service. Use the same settings in
two terminals:

```bash
uv run --frozen panestria local serve --config /ABSOLUTE/PATH/local.json
uv run --frozen panestria tui --config /ABSOLUTE/PATH/local.json
```

The first command stays running. In the TUI, ask a short synthetic question such
as “Reply with READY.” The ordinary answer flow stays the same. Authenticated
`GET /v1/local/status` now contains `model_manifest`. An existing owner Ask JSON
command/API response and `GET /v1/ask/{request_id}` receipt contain the retained
`model_manifest` and completed `usage.model_manifest_sha256`. A metadata receipt
has no answer text; replay never generates again. Do not paste bearer tokens
into messages or commit private settings.

Expect exact hashes for the model bundle, weights, template/system layers,
engine/library/bridge artifacts and license references, plus supported text/no-tool
capability, context bound and fixed CPU generation/capacity profile. The tokenizer
is identified by its containing GGUF artifact, **not** a separately extracted or
universally interchangeable tokenizer. `evaluation: NOT_EVALUATED` is deliberate:
identity is not accuracy, readability, preference, measured fit or release proof.
Startup hashes runtime files once using cached public artifact observations;
ordinary foreground resource admission still runs for every question.

Missing/mismatched identity refuses execution/completion instead of falling back.
Binding is one-time for a provider; changing new-work defaults does not rewrite an
active request. Returning to the original supported provider/configuration keeps
the original context/memory data. There is no hot-swap/default-replacement command,
automatic retry, cache transfer or adaptive selection. Bound work must keep using
a manifest-aware version of the application. General and selected profile Ask use
the same boundary; profiles still need separate current qualification/approval,
and restricted response hashes remain omitted. This setting grants none of those.
With the field false/omitted, legacy behavior remains unchanged. The historical
observer on8770 was not upgraded or restarted by this implementation.

Relevant component checks, with explicit model/runtime/capacity fixtures:

```bash
uv run --frozen pytest tests/unit/test_model_manifest_contract.py \
  tests/integration/test_pinned_model_manifest.py -m 'not live' -q
```

The optional `test_actual_cached_cpu_manifest_startup_ask_and_receipt` live node
requires an explicitly selected existing read-only cache via
`PANESTRIA_PROFILE_TEST_MODEL_CACHE`. It preserves pre-existing model services,
uses only its disposable PG project/container and one actual CPU generation,
then shuts down its own model. Its PG/Unix-socket/ASGI observation does not certify
physical TCP, OS secret storage, answer quality or the original G1/G3 gates.
See [source-bound observations](../../evidence/pinned-model-manifest-2026-10-22/report.json).
