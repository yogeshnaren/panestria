# Run an accepted PUBLIC Build from Mission Control

This explicit mode connects plan review to the existing finite one/two-worker
Claude subscription runner. It needs an already configured private Build project
and **current** runtime qualification. It does not install/authenticate a provider,
refresh certificates, select another account, or start the quota background queue.
Default observer and the existing review website stay unchanged.

Use current `main` after this task is merged. Prepare your own disposable PUBLIC
Build project using [native plan execution](NATIVE_PLAN_EXECUTION.md) and
[PUBLIC plan staging](PUBLIC_PLAN_STAGING.md). Preserve the private Build config,
its reviewed checks, protected repository and original evidence. Do not point a
test at your daily review project/database or use old qualification as current.

From the checkout, build the dashboard with the documented pinned toolchain:

```bash
uv sync --frozen --group dev
npm --prefix apps/mission-control ci --ignore-scripts --no-audit --no-fund
npm --prefix apps/mission-control run build
```

Create dedicated activity settings for the **same owner/project IDs** as your
private Build config, on an unused loopback port. Use your existing private
database environment; never paste its value into a browser or commit it.

```bash
uv run panestria activity init --directory /absolute/private/mission-run \
  --owner-id OWNER_UUID --project-id PROJECT_UUID --port 8772
uv run panestria mission-control serve \
  --config /absolute/private/mission-run/activity.json \
  --assets "$PWD/apps/mission-control/dist" \
  --build-run /absolute/private/build.json
```

Leave that foreground server terminal open. In another terminal:

```bash
uv run panestria mission-control pair-code \
  --config /absolute/private/mission-run/activity.json
```

Open the origin printed by the server and enter that one-use pairing code.
Never enter provider credentials or an API key. This mode has a separate session
from observer/intake/review modes and cannot be combined with their flags.

1. Import/stage a complete PUBLIC zero-API-cash contract/proposal/inventory bundle,
   or inspect a retained plan by ID. Review every check, path, DAG, hash and limit.
2. If proposed, separately check the exact plan acceptance box and press **Accept
   exact plan**. Expected: ACCEPTED with CREATED tasks, **no execution yet**.
3. In **Run this accepted plan**, separately authorize the bounded subscription
   run and press **Start finite Build run**. Expected: a retained original request
   ID, then REQUESTED / CLAIMED_UNCONFIRMED, followed by a controller return when
   available. No new paid fallback, automatic rerun or merge is enabled.
4. Successful independent final checks produce **WAITING_APPROVAL**, goal ACTIVE.
   Open the goal's protected diff/check review. Review and consent remain separate
   actions; final merge uses the existing exact owner Build CLI workflow.
5. To withdraw, check the cancellation box and press **Cancel this Build plan**.
   CANCELLING/held claims can remain until real physical evidence proves release.
   A controller return does not prove physical stop or grant task completion.

On a lost reply, inspect the same plan/run request. Polling and reload use GET
only. A still-unclaimed REQUESTED action can be explicitly started using its
original request before its 90-second admission deadline; replay cannot renew
the deadline. Claimed/returned requests cannot start again with another nonce.
Use existing operator inspection/reconciliation for uncertain/already attempted
work. Do not clear events, reset leases or replace old evidence to force progress.

If admission is denied, inspect current policy, protected base, exact runtime
qualification/inventory, capacity and the terminal status/evidence commands.
`ADMISSION_DENIED` is not a runtime pass. A configured storage warning appears
with observed bytes and warning codes; review [storage recommendations](STORAGE_AWARENESS.md).
Panestria does not delete anything. Stale/unknown quota and billing observations
are not refreshed by this explicit foreground mode and grant no background work.

Component check, requiring the existing disposable Docker test setup/Chromium:

```bash
uv run pytest tests/integration/test_mission_build_run.py -q
```

This runs real local infrastructure with explicit non-live native/auth/certificate/
capacity fixtures. It sends no provider inference and is not G1/G2/G3 acceptance.
The real owner trial and remaining revision-3 work remain required.
