# Enable the shared charter in offline Ask

The existing data-free assistant charter can now be used in ordinary offline
Ask as well as explicitly enabled profile Ask. It asks for honesty, uncertainty,
fact/citation preservation and respectful correction; it grants no permission or
claim that the model follows those instructions correctly.

Use your existing private `local.json` from [local Ask setup](LOCAL_ASK_SETUP.md).
Stop/restart only your own local Ask server when convenient. Add this Boolean
setting while preserving every existing ID, path and credential:

```json
"assistant_charter": true
```

This is a field in the existing JSON object, not a replacement file. Keep the
file private. No setting or owner server is changed automatically by this task.
False or an omitted field keeps the original general renderer.

Run the same existing command:

```bash
uv run panestria local serve --config /absolute/private/local.json
```

Use the existing keyboard Ask or Mission Control Ask configuration to connect.
Your authenticated local status now reports `assistant_charter` as
`SHARED_DATA_FREE_V1`. Ask a normal question; expected behavior remains a local
answer and canonical receipt, with no cloud fallback and no retained answer by
default. The prepared context now includes the fixed charter alongside untrusted
reference data. Do not infer accuracy/style quality from a completed receipt.

Enabling this setting does not enable profile storage, create a key or share
your private preferences. To use an encrypted profile, follow the existing
[qualified profile service](QUALIFIED_PROFILE_SERVICE.md) and
[profile Ask terminal](PROFILE_ASK_TERMINAL.md) instructions with current real
qualification. The local config referenced by that service carries the same
setting; its private style overlay includes the charter once. Existing local
consent/purpose/field selection and response fingerprint omissions still apply.
An old certificate is not refreshed by editing this setting or upgrading source.

Context size includes the charter. If the full question, mandatory rules or
pinned references cannot fit, expect a refusal before model generation. Explicitly
choose a supported larger context (up to the existing4096 limit) or shorten the
question; do not erase pins/rules to force a response.

Changing the setting affects new requests. Already prepared requests retain
their original context bytes; repeated completed requests inspect their receipt
and do not run inference again. This component does not enable model replacement,
export private context, qualify style fidelity or complete MVP acceptance.

Focused component checks, with the existing disposable PostgreSQL setup:

```bash
uv run pytest tests/integration/test_local_charter_context.py -q
```

Provider/process/keys/capacity in these checks are explicit non-live fixtures.
