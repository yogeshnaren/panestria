# Select a reviewed Claude Build model

Panestria can request a specific model for an explicit PUBLIC one/two-worker
Build. Existing configurations stay on Haiku. This does not enable background
work, qualify a model or show that your account can use it.

Explicit request IDs are `claude-haiku-4-5-20251001`, `claude-sonnet-5` and
`claude-opus-5`. Aliases such as `opus`, `sonnet`, `best`, `default`, `opusplan`,
Fable and custom IDs refuse. Failed requests do not trigger another Panestria
model/provider. Requested and native-reported identities remain separate from
weights, quality, quota and cash.

Use the existing [owner Build setup](OWNER_BUILD_CLI.md) and
[connection guide](NATIVE_CONNECTION_GRANTS.md). Before intentionally using an ID:

1. On a clean checkout, qualify that exact source/model with the existing private
   subscription login. This command runs the fixed PUBLIC OS/native conformance
   fixture and consumes subscription inference; it is not a metadata-only probe:

   ```bash
   uv run --offline --frozen panestria native qualify-build \
     --evidence-directory /absolute/private/model-qualification \
     --model claude-sonnet-5 --public-subscription-smoke
   ```

   Continue only on actual PASS. Preserve the original report and use its returned
   certificate hash/directory. Quota, authentication, unavailability or conformance
   failures stay failures; never substitute a legacy certificate.
2. Deliberately set `"native_model": "claude-sonnet-5"` in the private0600 Build
   config and select its current exact certificate. Complete existing separate
   policy review. A model setting alone authorizes no task or connection.
3. Use `connections native-template` as documented. It derives schema3 and the
   exact request from that config. Review the visible model, account, policy,
   claimed certificate, configuration, original expiry and bounds in the terminal
   before its separate decision. Select the recorded grant/version and original
   account-observation hash in the private config.
4. Create/review a fresh plan/inventory for those settings and run existing explicit
   `plan run ... --public-subscription-run` or single-worker Build. Old plans,
   grants and certificates are not upgraded. Expect WAITING_APPROVAL only after
   all independent final checks; continue exact Build review/merge. Retained
   native receipts or explicitly captured offline references show the separate
   requested/reported models.

Expect `selected_model_requires_reviewed_native_connection` without a matching
selection. Different displayed models, certificate, inventory, grant, account,
policy or expired authority refuse further work. Native model mismatch stops
transport; permission to select a model does not accept its output. Background
commands return `background_selected_model_not_supported` with these foreground
settings until separate model-scoped queue support exists.

Provider-free developer checks:

```bash
uv run --offline --frozen pytest -q \
  tests/unit/test_selected_native_model_contracts.py \
  tests/integration/test_native_model_selection.py -m 'not live'
```

The connected test uses actual disposable PG/Git/MCP/Docker and synthetic native,
account/auth/certificates. Separately selected `zero_turn_empty_auth` cases use
the actual pinned binary with fresh empty auth and zero turns; no inference,
tool execution or certificate issuance. [Original component evidence](../../evidence/native-model-selection-2026-10-23/report.json)
retains failures/corrections and scope. No owner settings/services changed,
billing evidence was not refreshed, and G1/G2/G3 remain unpassed.
