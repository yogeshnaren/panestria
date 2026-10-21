# Finite background native execution

Keep the existing task/attempt/claim/invocation/handoff/evidence/approval protocol
as task authority. A new immutable `BackgroundRun` is only a bounded coordinator
reservation over one exact queue binding and account link; it is not a second
task-state store or a dispatch token. Current native policy/certificates still
authorize actual effects. There are no migrations or autonomous merge actions.

A workstation session advisory lock serializes finite background controllers.
Fleet/project transactions append start/return facts, recheck eligibility and
claim through the existing scheduler atomically. Crash drops the session lock
but retains the unfinished fact and every task claim. Explicit safe-stop
reconciliation requires the session lock and no held/unreturned canonical work;
it grants no claim-release or inference authority. An exception likewise cannot
turn unknown cleanup into a released task slot.

The native driver gets protected overridable claim/operation-lock hooks, retaining
the foreground path's two workers and ordinary operation lock. The background
driver uses one worker and a separate local operation lock, re-probes the exact
personal subscription principal before each claim, and yields new claims to
foreground Ask/held Build work. It retains completed intermediate handoffs and
uses them only on an explicit bounded resume. No automatic retry or provider switch.

No-extra-spend admission requires a fresh explicit disabled-setting owner report
for the reviewed linked account; missing/unknown/enabled/stale reports deny.
This is owner evidence, not provider-attested billing proof or a CLI cost estimate.
Actual background inference remains disabled/unqualified until the owner's real
setting and runtime prerequisites are met. Fixture admission is not live evidence.

The original aggregate wall budget spans explicit coordinator resumes, with the
policy/report deadline covering a full prospective node envelope. Quota basis
identifies immutable observation IDs, preventing reuse as unspent quota by another
item. Native limit signals are stored without fabricated numeric balance/reset;
new overlapping-window evidence is required to clear the signal. Foreground slots,
task attempts, source/epoch fences and unknown holds are never widened by this layer.

[Runbook](../testing/BACKGROUND_RUN.md),
[source-bound evidence](../../evidence/background-run-2026-10-21/report.json).
