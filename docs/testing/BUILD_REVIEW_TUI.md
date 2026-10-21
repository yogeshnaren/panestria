# Review PUBLIC Build work in the terminal

Prepare and submit one bounded exercise using the existing
[owner Build CLI](OWNER_BUILD_CLI.md). Its private `build.json`, migrated
database, explicit PUBLIC policy and runtime qualification remain prerequisites.
This is a review screen for an existing goal; it does not start Claude, select
new work, grant permissions or submit a contract.

In another terminal with the same private database environment:

```bash
uv run --frozen panestria build tui \
  --config /absolute/private/build.json GOAL_UUID
```

Expect **PUBLIC BUILD REVIEW** and the actual task state. This uses the existing
owner CLI against canonical state, not the offline Ask server or browser demo.
It requires an80-column by18-row terminal. Snapshots are explicitly refreshed;
the displayed last state can become stale as another process changes the task.

- **Tab** switches between independent checks, diff and exact approval preview.
  **PgUp/PgDn** scroll. Diff/check text cannot execute terminal escapes or actions.
- **a** opens a frozen merge review. Inspect the full owner/project/action,
  base/candidate/check/policy/expiry preview and effect digest. Nothing is sent
  merely by opening it. Type **MERGE**, then **Enter**, to approve that exact
  displayed digest/version through the existing protected merge operation.
- **c** opens cancellation review. Type **CANCEL**, then **Enter**. The existing
  kernel rechecks the displayed task version; the UI does not invent cancellation.
- **Escape** discards an unsent confirmation. **F5** discards it and refreshes.
  A stale preview is never silently replaced with a newer approved action.
- **q** outside confirmation or **F10** anytime closes the view. During a decision,
  quit twice acknowledges leaving
  an unconfirmed outcome. Closing the client stops only its own CLI child;
  it cannot undo an effect already committed. Reopen and refresh canonical state.

After a decision, only a new successful canonical read supplies the displayed
task state. Timeouts, access/configuration loss and lost acknowledgements clear
the view and show UNCONFIRMED; there is no automatic mutation retry. A pending
or partially confirmed effect requires existing reconciliation/inspection, not
another blind approval. COMMITTED/COMPLETED requires the existing protected CAS.
The original working checkout is preserved; inspect/import its separate approved
protected result as described in the owner CLI guide.

The app retains no history or export. Terminal recording/physical erasure is
outside this promise. An expired runtime certificate or changed policy/check
bundle can refuse merge; do not relabel old native evidence or widen permissions.
This component does not complete G1, full R3 Mission Control or owner acceptance.

Focused checks use actual PTY/keyboard, owner CLI, disposable Postgres, Docker,
Git/diffs/checks and protected CAS. Native generation and certificates are
explicit TEST_FIXTURE_NOT_LIVE fixtures; no provider turn is repeated:

```bash
uv run --frozen pytest tests/integration/test_build_tui.py \
  tests/integration/test_ask_tui.py tests/integration/test_owner_build_cli.py \
  -m 'not live' -q
```

## Canonical plan progress

For a canonical plan goal, press **p** or Tab to the fourth view to load verified Build progress on demand. The bar counts original **final required checks**, followed by execution/attention/next action, separate owner merge and release acceptance, conservative repair envelope and held/UNKNOWN capacity. PgUp/PgDn shows original check/non-goal and milestone/candidate evidence references. It uses the same existing private Build configuration and scoped goal; no extra setup or provider call is needed.

The read-only view reports its own as-of event cursor and can become stale. It never updates approval optimistically, submits work, retries a failed model or grants recovery. F5 discards the views and pending confirmation, then refreshes canonical task status. Press p again for fresh progress. Approval still freezes the exact status digest/version and requires typing MERGE; cancellation still requires typing CANCEL. A failed progress read clears only the progress observation and cannot turn into approval. An old single-worker goal without canonical plan membership can still use its original check/diff/review pages; its plan-progress view is UNCONFIRMED.

The same read is available as JSON:

```bash
panestria build progress --config /absolute/private/build.json GOAL_UUID
```

For a create-once private snapshot and SHA256, use [the progress export command](BUILD_PROGRESS.md). Non-goals and release acceptance remain NOT_ASSESSED. [Actual terminal evidence](../../evidence/progress-terminal-2026-10-20/report.json) covers real PTY/Postgres/Docker/Git and independent checks, with explicit native/auth/capacity fixtures. No new model/provider call or full Mission Control/G3 claim.
