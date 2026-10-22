# Stage a PUBLIC Build plan in Mission Control

This optional desktop mode lets you import a plan produced with the existing
[Build preflight](BUILD_PLAN_PREFLIGHT.md) or local planning workflow. It validates
and saves the contract, proposal, inventory and pending plan consent. It does not
start Claude, accept the plan, change policy or merge code. Runtime qualification
is NOT_ASSESSED. Use PUBLIC content only; no credentials or private source text.

Use current `main`, Python dependencies and the production dashboard build from
[observer setup](MISSION_CONTROL_OBSERVER.md). Keep the existing private activity
settings, selected owner/project and `PANESTRIA_DATABASE_URL`. Choose an unused
loopback port in a separate activity config if another dashboard is running.
Do not stop or reuse the owner's review service just to try this mode.

1. Prepare private `goal.json`, `plan.json`, `inventory.json` as described in
   [PUBLIC plan staging](PUBLIC_PLAN_STAGING.md). Use a new PUBLIC goal, version1,
   zero API cash and exact current project policy. Inventory declarations do not
   certify the installed worker; actual execution validates its own prerequisites.
2. Run the existing `panestria plan validate OWNER_UUID PROJECT_UUID --contract
   /absolute/private/goal.json --inventory /absolute/private/inventory.json
   --proposal /absolute/private/plan.json` preflight.
3. Assemble a JSON file with exactly three keys: `contract_document` containing
   the complete goal document, `proposal` containing the complete plan document,
   and `inventory` containing the complete inventory document. Preserve all IDs,
   hashes, checks, scope and limits. Keep it private and out of Git. The entire
   request, including the PUBLIC acknowledgment, must fit65536 UTF-8 bytes. Larger
   canonical files remain usable through the existing CLI; this UI doesn't widen
   its transport cap.
4. Start the explicit mode in a terminal (it remains a foreground process):

   ```bash
   panestria mission-control serve --config /absolute/private/activity.json --assets /absolute/repo/apps/mission-control/dist --build-intake
   ```

5. In a second terminal, run `panestria mission-control pair-code --config
   /absolute/private/activity.json`. Open that config's printed loopback URL and
   enter only the one-use code. Never paste the bearer token.
6. In **Build · stage a PUBLIC plan**, load the bundle file or paste the JSON.
   Review the entire input. Confirm the PUBLIC/staging-only checkbox, then press
   **Stage PUBLIC plan** once.

Expect `STAGED_NO_EXECUTION`, goal CREATED, plan PROPOSED, exact retained contract,
proposal/inventory/validation, pending consent digest and expiry. No task, attempt
or worker is allocated. Invalid scope, hashes, DAG, budget or stale policy denies
staging atomically. Other modes and generic goal/Ask/accept routes stay unavailable.

If a reply is UNCONFIRMED, copy the displayed plan UUID and press **Inspect staged
plan**. A reload clears all input and response content; paste that UUID into
**Recover staged plan by plan ID**. GET recovery never reissues the POST. Do not
create another plan to work around an ambiguous reply. Missing/unconfirmed state
needs inspection, not an automatic retry. Canonical plans remain retained in the
selected database; the browser uses no local/session storage.

To proceed, inspect and separately accept the exact pending digest using the
existing [owner CLI](PUBLIC_PLAN_STAGING.md). Consent expires after15minutes;
replay doesn't refresh it. Acceptance only creates CREATED tasks. Qualified
[scheduling/native execution](NATIVE_PLAN_EXECUTION.md), independent final checks,
owner final review and exact merge remain separate actions. This screen exposes
no accept/run/merge button. It can later inspect ACCEPTED if the owner accepted
through that separate workflow.

Focused connected checks:

```bash
uv run --frozen pytest tests/integration/test_mission_build_intake.py tests/integration/test_public_plan_submission.py tests/e2e/test_aos_005.py::test_openapi_matches_the_mounted_routes
```

Build the production assets first and use a supported Node/installed Chromium as
in the observer guide. The fixture uses disposable PG55439 and owned random
ports, actual HTTP/CLI/Chromium, declared synthetic worker inventory and explicit
lost reply injection. No intake model/worker/provider/search call or live
qualification is claimed. Preserve owner databases/services. Full AOS-028,
remaining revision-3 work, original cumulative gates and the real owner trial
remain required before R3 acceptance.

The separate [plan review mode](MISSION_PLAN_ACCEPTANCE.md) adds explicit exact
plan acceptance through the same canonical service. It requires a different
launcher flag and session; this staging-only mode remains unchanged.

A server-confirmed **REJECTED BEFORE COMMIT** unlocks correction and clears your
PUBLIC acknowledgment. This request changed no canonical data: correct/review the
bundle and explicitly submit again with its same plan ID. No automatic retry is
sent. Malformed goal contracts return a bounded validation refusal. An absent
rollback acknowledgment, lost COMMIT reply or post-commit inspection error stays
UNCONFIRMED and still requires GET recovery of the original UUID. A status409 or422
alone never proves a request did not commit.
