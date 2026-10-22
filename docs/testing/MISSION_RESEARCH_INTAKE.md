# Stage a PUBLIC Delegate question in Mission Control

This mode provides a distinct Delegate input using the existing local staging
service. It retains an explicitly PUBLIC question, fixed contract and bounds,
then shows the actual CREATED goal/task and request IDs. It starts no search,
model, collection, synthesis, worker, approval or effect. Full Delegate execution
and factual support remain separate; the live search setup is still deferred.

The default observer and offline Ask mode keep their own authority. No setting
widens your existing Ask project. Keep the owner's8770 review server unchanged.

## Prepare existing scope and select the exact template

Use a migrated database, existing owner/project/current policy, frozen Python
environment and the production frontend from this same source. Build it as in
the [observer guide](MISSION_CONTROL_OBSERVER.md); use its supported Node/npm
versions. Load your existing private database environment in the terminal.

Use the reviewed contract and bounds from
[local PUBLIC staging](OWNER_RESEARCH_SUBMISSION.md). Keep required checks and
the exact current policy reference. Use a dedicated research project when later
execution is intended. An offline project may permit local staging while refusing
all network execution. A different policy never upgrades a pinned contract.

Prepare a private mode0600 `research-intake.json` with this shape:

```json
{
  "schema_version": 1,
  "root": "/ABSOLUTE/EXISTING/PRIVATE/RESEARCH_CAS",
  "contract_template": {"REPLACE_WITH": "your complete valid PUBLIC GoalContract"},
  "limits": {
    "max_sources": 2,
    "max_source_bytes": 65536,
    "max_total_bytes": 131074,
    "max_redirects": 2,
    "deadline_seconds": 60.0
  }
}
```

The placeholder is not a runnable contract: insert your complete existing
contract, including stable owner/project IDs, a valid UUIDv4 placeholder goal ID,
required acceptance checks, budgets, paths/capabilities and current policy ref.
At submission only that goal ID changes. No other contract/bound is editable from
the browser. Select an existing canonical private mode0700 CAS root. The mode
creates no root/project/policy, downloads nothing and needs no search certificate
merely to stage. It refuses unsafe files/roots, invalid versions and non-PUBLIC
or mismatched owner/project templates. Configuration stays frozen until restart.

Create separate activity settings on an unused port with the template's scope:

```bash
uv run --frozen panestria activity init \
  --directory "$HOME/.panestria-research-intake" \
  --owner-id OWNER_UUID --project-id PROJECT_UUID --port 8773

uv run --frozen panestria mission-control serve \
  --config "$HOME/.panestria-research-intake/activity.json" \
  --assets "$PWD/apps/mission-control/dist" \
  --research-intake /ABSOLUTE/PRIVATE/research-intake.json
```

Leave the foreground process running; Ctrl+C stops it. An occupied port refuses
startup. This is local desktop loopback only, with a separate session purpose
bound to the selected template/store/bounds. Do not combine this mode with Ask,
Build review or protected Build evidence flags. No persistent scheduler starts.

In another terminal with the same checkout/database environment:

```bash
uv run --frozen panestria mission-control pair-code \
  --config "$HOME/.panestria-research-intake/activity.json"
```

Open http://127.0.0.1:8773/, enter the eight-character one-use code within120seconds
and choose **Pair**. Observer/review/Ask cookies do not authorize this mode.

## Stage and recover

1. Expand **Exact owner-selected contract and bounds**. Inspect the full contract,
   policy, capabilities, budgets and required checks. The template digest binds
   the selected configuration. Existing checks are retained, never auto-passed.
2. Enter a PUBLIC question, at most4096UTF-8 bytes. Confirm the checkbox only after
   reviewing the content and bounds. **Stage PUBLIC question** creates one new
   goal UUID and one canonical staging operation. This disclosure decision is
   explicit; the input does not classify private content as safe automatically.
3. Expect **STAGED_NO_EXECUTION**, the retained literal question, request/task IDs,
   actual goal/task state and stored bounds. Newly staged work is CREATED with
   NOT_ASSESSED semantic support. No task attempt/lease, network or inference
   starts. A later inspection can show changed canonical states after independent
   owner work; the staging receipt never asserts current execution is absent.
4. Copy the goal ID. If the response fails, the operation is **UNCONFIRMED** and
   another submission is blocked. **Inspect staged question** reads the same goal
   through the verified private store; it does not POST/retry or start research.
   A committed operation with a lost reply can be recovered without duplicate
   rows/events. If no receipt can be confirmed, inspect database/service health
   before considering another submission.
5. Reload discards memory-only form/CSRF state. Pair again for mutation/logout
   controls; existing cookies can read a saved goal under **Recover staged question
   by goal ID**. **New PUBLIC question** clears the confirmed previous view and
   allows a separate manual submission. Log out to revoke/clear the view. No
   question, CSRF or receipt is saved in browser storage or URLs.
6. Continue later using the existing `research inspect` and qualified collection
   workflow. This staging mode does not install search, fabricate a certificate,
   grant execution or complete R2/G2/R3/G3 or the real owner trial.

## Verification

```bash
uv run --frozen pytest tests/integration/test_mission_research_intake.py -q
```

Uses actual Chromium/physical HTTP/PostgreSQL/CAS and the CLI pairing command on
disposable test resources. Search/fetch/reader calls are explicitly forbidden.
One injected post-commit reply failure tests same-goal GET recovery. Missing
public intent, altered bounds digest, CSRF, stale policy and final session denial
cannot commit another goal. The required checks/CREATED state are retained.
Source-bound results and original failed observations are indexed under
`evidence/mission-research-intake-2026-10-22/report.json`. No provider/model call,
fake live qualification or owner-data migration is part of these tests.
