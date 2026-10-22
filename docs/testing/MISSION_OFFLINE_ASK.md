# Offline Ask in Mission Control

This explicit mode connects Mission Control to the existing local Ask runtime.
It runs one configured local model, shows its answer and measured receipt, and
supports cancellation and receipt recovery. It enables no Claude/cloud route,
profile context, Delegate or Build submission. The ordinary metadata observer
still cannot run a question. The owner's existing observer on8770 is unchanged.

## Run with an existing offline Ask setup

First complete [local Ask setup](LOCAL_ASK_SETUP.md): private settings, migrated
dedicated project/database and the already prepared pinned model cache. This
mode does not download a model, initialize a database or reuse a running model
container. Do not run a second model service alongside your existing local Ask
server; stop your own foreground instance with Ctrl+C before selecting this UI.
An occupied port or existing model service refuses startup without killing it.

Build the production frontend with the supported Node/npm versions from the
[observer guide](MISSION_CONTROL_OBSERVER.md), using the same source checkout:

```bash
npm ci --prefix apps/mission-control --ignore-scripts --no-audit --no-fund
npm run build --prefix apps/mission-control

uv run --frozen panestria local serve \
  --config /ABSOLUTE/EXISTING/PRIVATE/LOCAL_CONFIG.json \
  --mission-assets "$PWD/apps/mission-control/dist"
```

Load your existing private database environment in this terminal as described in
local setup. The service remains in the foreground; leave it running while using
the page. Ctrl+C stops its owned runtime. `--mission-assets` selects this mode;
omitting it preserves the original plain local Ask page. This mode currently
requires127.0.0.1 and refuses combined profile/review modes. No LAN/phone access
is enabled. Compiled assets must be local, complete and bounded.

In a second terminal with that same environment/check-out:

```bash
uv run --frozen panestria local pair-code \
  --config /ABSOLUTE/EXISTING/PRIVATE/LOCAL_CONFIG.json
```

Open the loopback URL/port from your local configuration, enter the one-use code
within120seconds and choose **Pair**. This mode has its own cookie and session
purpose: observer/plain-Ask/review sessions do not authorize it. Keep tokens and
credentials out of the page/URLs. Do not replace the existing8770 observer's
settings or launcher with local Ask settings.

## Test and expected results

1. **Offline Ask** appears after pairing. Ask a short, nonsecret question using
   the **Question** field and **Ask offline**. UTF-8 input is limited to4096bytes,
   output to128tokens, and execution to60seconds. Initial model loading can take
   time. There is one request ID and no automatic retry/provider fallback.
2. A successful request shows **COMPLETED**, its literal answer, model/context/
   trace identifiers and actual measured usage. Failure/refusal shows its actual
   canonical state/code; it never becomes a successful answer. These states do
   not qualify the runtime or the MVP release. Treat model output as untrusted.
3. Copy the **Request ID**. During a slow request, **Cancel request** asks the
   canonical controller to stop it. Only a confirmed terminal response permits
   a new question. A lost cancellation response remains unconfirmed.
4. **Stop waiting** closes the browser response without claiming cancellation.
   Timeout/disconnect also leaves the request unconfirmed. **Inspect receipt**
   reads that same ID; it never starts inference. While its outcome is unknown
   or active, the view blocks another question. If the server has no receipt,
   check server health/terminal first; do not blindly resubmit ambiguous work.
5. After a confirmed terminal state, **New question** clears current text. A
   page reload discards the question/answer and memory-only CSRF value. Enter a
   saved ID under **Recover receipt by request ID** and inspect: canonical
   metadata is available, but the answer cannot be recovered because it was
   never retained. Pair again to restore submit/cancel/logout controls.
6. **Log out** revokes the session and clears the private view. Questions and
   answers are never placed in browser storage, URLs or the activity ledger.
   No durable conversation history or encrypted profile context is enabled.

For an actual local model readiness/quality check, use the existing local setup
and inference qualification instructions. The focused tests below use explicit
nonlive model/process/hardware fixtures; they cannot qualify actual inference:

```bash
uv run --frozen pytest tests/integration/test_mission_offline_ask.py -q
```

They use production assets, cached Chromium, physical loopback HTTP, a real CLI
pairing-code command and isolated PostgreSQL55439. They exercise inert hostile
answer text, no retention, canonical cancellation, ambiguous response recovery,
no redispatch/fallback and model refusal. Do not run55439 suites concurrently.
Source-bound original reports are indexed in
`evidence/mission-offline-ask-2026-10-22/report.json`.
