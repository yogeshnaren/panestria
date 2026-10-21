# Run one bounded background job

This command connects the [reviewed queue](BACKGROUND_WORK_QUEUE.md) and
[account link](BACKGROUND_ACCOUNT_LINK.md) to the existing qualified PUBLIC
Claude native plan driver. It executes one selected item, with one worker at a
time, and returns to the terminal. It does not merge, enable a daemon, select a
different provider/model or turn a subscription into an API credential.

Before running, the accepted plan must still match its frozen queue binding.
The private policy must include a fresh **explicit owner report** that usage
credits/extra usage are disabled for that same linked account, plus admissible
quota windows or the separately reviewed unknown-balance best-effort policy.
Do not fill in the billing report by assumption: inspect the actual account's
setting. Queue/link metadata, a dollar cap and synthetic test results do not
prove it. This implementation neither reads nor changes the billing setting.
An unstarted item's policy can be renewed only by withdrawal and fresh review.

Existing Build configuration, current runtime/source qualification, independent
checks, privacy/permission and exact plan acceptance remain mandatory. The owner
reported the dedicated account's extra usage disabled on2026-10-21. This is
owner-reported evidence with its original freshness limit, not provider
attestation or an automatically renewed setting check.

The [actual subscription journey](../../evidence/background-owner-journey-2026-10-21/report.json)
at clean `2c5aede` completed one PUBLIC synthetic queued job with two serial
Claude workers, five returned invocations, independent final checks, wrong-digest
rejection and exact scripted test-owner merge. Opt-in runtime measurements and
an offline confirmed-result reference were saved; training export stayed denied.
Quota balance stayed UNKNOWN under an explicit bounded best-effort policy.
The original failed job (an unavailable `hexdump` diagnostic) is preserved;
worker instructions now describe Bash builtins/installed Python instead of
assuming optional utilities. No failed task was silently retried. This one
journey does not establish all foreground-pressure/restart/limit cases or G3.

```bash
panestria background run --config /absolute/private/build.json \
  ITEM_UUID --allow-background-subscription-run
panestria background runs --config /absolute/private/build.json ITEM_UUID
panestria build tui --config /absolute/private/build.json GOAL_UUID
```

To inspect the next **unstarted** candidate without running anything, then
explicitly execute at most that one eligible job:

```bash
panestria background next --config /absolute/private/build.json
panestria background run-next --config /absolute/private/build.json \
  --allow-background-subscription-run
```

Priority3 is highest; ties prefer earlier known reported resets, with unknown
reset last, then older queue sequence. `next` returns a read-only candidate,
not a dispatch guarantee. `run-next` rechecks all existing runtime/account/
policy/billing/quota/storage/foreground gates; a race, denial or failure returns
without trying another job. Previously started work needs the explicit item
inspection/resume command. Pending final review keeps its canonical claim.
This is one finite command; no timer or service is installed. See the
[selection design](../design/73-BACKGROUND-SELECTION.md) and
[connected evidence](../../evidence/background-selection-2026-10-21/report.json).

Expected results:

- `WAIT`: inspect `reason`/`background_wait_reason`. Unknown/stale/insufficient
  quota, missing billing report, withdrawal, changed login, resource/storage
  limits, held capacity or foreground Ask stop new claims. Do not infer a model
  ran from a coordinator reservation.
- `WAITING_APPROVAL`: all worker handoffs and independent final-tree checks are
  retained for the existing exact owner review/merge. This command never approves.
- `STOPPED`/unconfirmed outcome: inspect canonical tasks, invocation receipts and
  held claims. No automatic retry, overflow or alternative provider follows.

Before each claim the controller observes the actual pinned/private login again
and requires the reviewed identity/profile/binary, fresh metadata, current policy,
all quota windows and the disabled-setting report. It conservatively requires the
full next-node wall envelope to fit before the report/policy/original job deadline.
Per-task attempt/wall limits and invocation fences are still enforced by the
existing scheduler and native controller. Resumes subtract recorded coordinator
time from the original job wall budget; they cannot reset it. A report already
used by another item cannot be counted as fresh unused quota for a second job.
Unknown best-effort remains separately explicit, with no invented balance/savings.

One PostgreSQL session advisory lock serializes background controllers on the
single canonical database. An immutable start fact retains the coordinator after
crash. Worker concurrency is one, leaving the second of the existing two slots
for foreground work. Any PREPARED/RUNNING Ask or held Build claim defers the next
background claim. A foreground arrival lets the bounded in-flight call finish
and preserves its real outcome/handoff; it pauses new work. It does not forcibly
kill a process or promise resources in other provider clients.

After foreground work clears, run the same explicit command to continue from
verified handoffs within the original budget. Completed workers are not repeated.
At most16 finite coordinator runs per item are retained. A native quota failure
records a labeled non-numeric route signal, no guessed balance/reset; subsequent
admission needs newer numeric eligibility evidence for every overlapping window.
Unknown/failed processes and claims still require existing reconciliation.

For a crashed controller, inspect `runs` for its exact `run_sha256`. Only after
the workstation session lock is free and canonical evidence shows **no active
claim or unreturned invocation**, explicitly record that it stopped:

```bash
panestria background reconcile-run --config /absolute/private/build.json \
  ITEM_UUID RUN_SHA256
```

This records coordinator return only. It releases no claim, changes no task
outcome and grants no dispatch/approval. An unknown invocation or held claim
refuses reconciliation. Do not delete events/claims or retry an ambiguous call.
Use the existing exact goal cancellation separately when cancellation is intended.
Withdrawal stops future background claims without cancelling the underlying goal.

The billing evidence is `FRESH_OWNER_REPORT_DISABLED_SAME_LINKED_ACCOUNT`, not
provider attestation. Public provider documentation and the owner setting report
remain distinct from observed inference/runtime qualification. Full TC06/07/10,
foreground resource qualification, S5/S7, automatic scheduling and G3 remain open.
The [component report](../../evidence/background-run-2026-10-21/report.json) retains
the original CLI serialization failure and corrected connected observations.

For finite opt-in polling instead of manual item selection, see the
[queue controller](BACKGROUND_QUEUE_CONTROLLER.md). It installs no scheduled service.
