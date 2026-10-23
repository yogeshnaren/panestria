# Review background work for a chosen model

Panestria can bind one finite background job to an exact reviewed native model
and independent account/model quota scopes. Existing fixed-Haiku items keep their
original meaning. This does not start a daemon, refresh consent, change billing
settings or automatically adopt a model.

First complete [model selection and qualification](NATIVE_MODEL_SELECTION.md),
the separate exact native connection review and a fresh accepted PUBLIC plan.
Use [the background controller guide](BACKGROUND_QUEUE_CONTROLLER.md) for the existing
account-link, exact-policy decision, finite controller and reconciliation steps.

1. Run existing `background draft --config PRIVATE_BUILD_CONFIG PLAN_ID ACCOUNT_ID
   --output PRIVATE_REQUEST`. With an explicit `native_model`, expect policy
   schema2 and the same exact `model_ref`; account `session`/`weekly` scopes have
   null models, and `selected-model` has that exact model. The draft starts nothing.
2. Inspect the private request. Use only truthful current quota/settings evidence.
   Billing defaults UNKNOWN; the draft cannot run. Retain independent sources,
   units and original observed/reset times. Add a fresh disabled-extra-usage owner
   report only after actually checking that account. Do not renew an old report
   or treat a dollar estimate/zero API cap as proof. All relevant windows must
   retain foreground reserves. Explicit bounded unknown best effort is a separate
   policy choice; it cannot supply unknown billing authority.
3. Use existing `background prepare`, exact policy hash/explicit enqueue and
   supported account metadata/link review. Check the full immutable binding/model,
   current waiting reasons, original expiry/budgets and requested-model field.
   A new selection requires a new deliberate item/review; do not edit stored facts.
4. Start only an eligible finite `background run` or bounded controller with its
   explicit subscription flag. Expect one worker at a time and WAITING_APPROVAL
   only after independent final-tree checks. No automatic owner merge occurs.

An account window above reserve cannot override a model window at/below reserve.
Unknown/stale billing, withdrawal, current foreground work, model/configuration
change, mismatched connection/certificate/inventory/account or observed exhaustion
stops new effects. `background_requested_model_changed` means the configured
model and immutable item/run differ; inspect that item rather than changing it.
Original handoffs/receipts survive a stop; existing held-claim reconciliation
still applies. `runs` exposes schema2/model separately from execution authority NONE.

Provider-free developer checks:

```bash
uv run --offline --frozen pytest -q tests/unit/test_background_model_contracts.py \
  tests/integration/test_background_model_scope.py tests/integration/test_background_run.py
```

Tests use real disposable PG/Git/MCP/Docker with explicitly synthetic native/model,
auth/account/billing/certificates. [Component evidence](../../evidence/background-model-scope-2026-10-23/report.json)
does not qualify actual provider/model availability, billing, quality, foreground
interference or release gates. The owner's billing observation is stale/background
OFF; search, real-phone setup and paid SDKTC04 remain deferred.
