# Explicit model selection for the PUBLIC verifier preflight

The existing semantic-support preflight previously requested only the legacy
Haiku alias. An optional exact model now allows a deliberately selected
subscription model to be evaluated against the same immutable PUBLIC corpus and
frozen rubric. This does not qualify any model, enable production claim judging,
send private material or complete AOS-022/G2/R3.

The accepted request identifiers are the existing closed `NativeModel` contract:
`claude-haiku-4-5-20251001`, `claude-sonnet-5`, `claude-opus-5`. An identifier is not
proof of account availability, provider weights, independent model family, quality,
price or extra-usage eligibility. No automatic choice, fallback or switch occurs.
Without an explicit selection, the original alias/profile and serialized legacy
observation shape remain unchanged; old reports/certificates are not upgraded.

The selected model binds the command and pinned read-only settings. Init metadata,
any assistant message and successful result usage must agree; absent/empty usage
cannot confirm a selected-model batch. Results retain requested and observed
identity separately, including unavailable outcomes. Skills/plugins/MCP/tools/API
keys/managed configuration, unexpected overage and changed control files remain
denied. A process result remains untrusted, and cash/quota remain UNKNOWN.

## Run only after a deliberate eligible evaluation decision

Use the existing pinned CLI/login and frozen dependencies. No installation,
credential, model download or provider substitution is part of these instructions.
Confirm the account's current extra usage/usage credits are disabled before any
actual subscription run. A stale billing observation or a Build connection grant
is not semantic-purpose permission. The implementation run for this task makes
**zero provider calls** and does not refresh billing or enable background work.

Choose one model using calibration, then freeze that choice/rubric before viewing
qualification outcomes. Do not tune on held-out labels, repeat failed quota/auth
calls, pool different models, or relabel historical observations. Run a separately
requested fold using the existing opt-in live test, for example:

```bash
PANESTRIA_RUN_NATIVE_ENTAILMENT=1 \
PANESTRIA_NATIVE_ENTAILMENT_MODEL=claude-sonnet-5 \
uv run --frozen pytest tests/integration/test_native_entailment_live.py \
  -m live -k calibration --junitxml=/absolute/private/calibration.xml
```

A separately authorized qualification uses `-k qualification` and a **different**
output path. Each fold starts at most one existing bounded process: 2 turns,
120 seconds, 256 KiB output, existing CLI USD0.25 estimate limit. That estimate
is not authoritative cash/entitlement enforcement; disabled extra usage and
current authorization remain prerequisites. Stop after refusal/uncertainty.

The test records structured predictions, score/denominators, requested/observed
model and original corpus/rubric/prompt/result hashes. Its passing assertion means
that a complete observation was retained, **not** that semantic accuracy passed.
The original local and Haiku quality failures remain intact. Even a better small
SNLI score does not prove research-domain partial/opinion/conflict/injection
behavior, independence from the drafting model or production/private eligibility.
Actual human research labels and calibrated role/acceptance integration remain
required. No task PASS, runtime certificate or training grant is minted here.

[Component evidence](../../evidence/public-verifier-model-selection-2026-10-23/report.json)
records controlled files/transport fixtures and explicitly excluded live cases.
