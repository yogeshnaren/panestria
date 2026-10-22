# Review and accept a Build plan in Mission Control

Use this separate opt-in desktop mode when you want to accept the exact retained
plan from the browser. The ordinary [Build intake](MISSION_BUILD_INTAKE.md) remains
staging-only. Existing review service8770 is unchanged. Start a separate config
on an unused loopback port with your existing selected owner/project/database.
No credentials, model download or worker execution is needed merely to review.

Follow the production dashboard setup and private bundle preparation in the
[Build intake guide](MISSION_BUILD_INTAKE.md), then start this mode instead:

```bash
panestria mission-control serve --config /absolute/private/activity.json --assets /absolute/repo/apps/mission-control/dist --build-plan-review
```

Get a new one-use code in another terminal with `panestria mission-control
pair-code --config /absolute/private/activity.json`, open the printed loopback URL
and pair. Intake/review sessions have different purposes; pair again when changing
modes. This foreground server stays running until you stop its own terminal.

Load and stage a PUBLIC zero-cash bundle, or enter an existing plan UUID under
**Recover staged plan by plan ID** and press **Inspect staged plan**. Read the full
expanded retained contract, every check/path/node/dependency, inventory and
budgets. Inventory declarations do not qualify an installed worker. Review the
exact consent digest and expiry. If you agree, select the separate acceptance
checkbox and press **Accept exact plan**. This is independent of staging's PUBLIC
acknowledgment and independent of eventual final merge approval.

Expect plan ACCEPTED, goal CREATED and canonical CREATED tasks. No attempt,
worker, inference, scheduling or merge is started. Expired consent, stale policy,
wrong digest, cross-origin/CSRF or revoked session denies the write. Repeating an
identical accepted request cannot create duplicate tasks or renew consent. The
server uses its current clock and canonical guards even if your browser clock
is wrong.

If the reply is **UNCONFIRMED acceptance**, use **Inspect staged plan** for the same
UUID. The UI sends no automatic acceptance retry. Only canonical ACCEPTED confirms
the decision committed; PROPOSED still needs review before any further manual
decision. Reload clears all content; recover by UUID and pair again before writes.
Content remains memory-only in the browser; canonical records stay in your DB.

After acceptance, follow the separately qualified
[native execution workflow](NATIVE_PLAN_EXECUTION.md). Actual source/runtime,
capacity, privacy and account prerequisites still apply. Independent final checks
and exact owner merge remain separate. This screen cannot execute or merge work.

Connected component checks (production dashboard/Chromium setup first):

```bash
uv run --frozen pytest tests/integration/test_mission_plan_acceptance.py tests/integration/test_mission_build_intake.py tests/e2e/test_aos_005.py::test_openapi_matches_the_mounted_routes
```

The fixtures use disposable PG55439, random owned ports, actual HTTP/CLI/browser,
synthetic inventory, one lost reply and a preparation-only expired-clock injection.
They do not certify native inference, the complete dashboard/inbox, original
release scenarios or R3 acceptance. Preserve owner services and original evidence.

**ACCEPTANCE REJECTED BEFORE COMMIT** means the server confirmed rollback of this
request. Inspect the same plan for a fresh review before another explicit decision.
This is different from an uncertain COMMIT or reply: those remain UNCONFIRMED and
block redispatch. The UI trusts a bounded explicit rollback marker, not status409
or422 alone. It never repeats an acceptance automatically.
