# Review and queue bounded preferred-provider work

This component records background intent for an **existing unstarted accepted
PUBLIC native Build plan**. It preserves the exact goal/plan/inventory/policy and
declared context hashes in the existing immutable PostgreSQL event ledger.
Task state, attempts, claims, approvals and outcomes remain in their existing
canonical records. Queueing does not start a worker or grant inference/spend.
The current component has **no background dispatcher or daemon**.

Use the same private Build config/database as the native-plan guide. Choose the
opaque local account reference used in your [quota observations](QUOTA_OBSERVATIONS.md).
It is a local metadata UUID, not an account enrollment, token or provider login.
Create a new file under an existing mode0700 private directory:

```bash
panestria background draft --config /absolute/private/build.json \
  PLAN_UUID ACCOUNT_REFERENCE_UUID --output /absolute/private/background.json
```

The draft derives owner/project/plan identity and original bounded wall envelope.
It creates request/policy UUIDs, uses account-wide session and weekly windows,
sets policy expiry one hour from the database clock, and leaves billing UNKNOWN.
It disables unknown/estimated-quota best effort by default. It creates no queued
fact or task/worker. The output is mode0600/create-once; an existing file is refused.

Read/edit the private request, then inspect its exact binding and current waits:

```bash
panestria background prepare --config /absolute/private/build.json \
  --request /absolute/private/background.json
```

Expect REVIEW_ONLY, the complete proposed binding, `policy_sha256`, and a
read-only eligibility view. Review categories (PUBLIC_BUILD, ARCHITECTURE_REVIEW
or TEST_DESIGN), job wall bound, expiry, reserves and billing/account scope.
Only existing Claude PUBLIC-native/trusted-integrator roles and zero API cash
are currently supported; it does not switch provider or select a new model.
A larger job needs a separately reviewed bounded plan; this policy cannot widen
its original accepted permissions or budget.

To record the exact policy as the local owner:

```bash
panestria background enqueue --config /absolute/private/build.json \
  --request /absolute/private/background.json POLICY_SHA256 --accept-background-policy
panestria background list --config /absolute/private/build.json
panestria background show --config /absolute/private/build.json ITEM_UUID
```

Enqueue atomically adds one immutable scoped binding event. Exact replay returns
the original event sequence without renewed freshness or another queued item.
A changed item ID/body/policy or a duplicate plan cannot silently replace it.
List shows the latest32 entries and total history count; show can inspect an
older item. The lifetime project history is capped at256 queued bindings; nothing
is pruned or deleted. Database rollback leaves no queued fact. No new schema or
parallel task-state store is used.

Withdraw the exact queued intent with its displayed binding hash:

```bash
panestria background withdraw --config /absolute/private/build.json \
  ITEM_UUID BINDING_SHA256
```

Withdrawal is idempotent and remains available after policy revocation. It does
not cancel the underlying goal, kill a process or release an uncertain claim.
Use existing exact goal/plan cancellation for that separate action.

For an expired policy on a plan that has never started, withdraw the old item,
draft a fresh request, review its new policy hash, and explicitly enqueue it.
The original queued and withdrawn facts remain immutable. A new item never
renews the old report freshness or resets the plan budget; any existing attempt
still prevents this renewal.

## Interpreting the eligibility view

- All requested quota windows are checked independently. Latest provider, owner,
  estimated and unknown lanes retain their labels; values are never added or
  converted between percentage, token and request units.
- Default regular-use floors are20percent,10000tokens or2requests in each matching
  unit. An observed amount at/below its floor waits. These are entry checks,
  not a promise about unknown future consumption or usage in other clients.
- `allow_unknown_quota: true` explicitly permits a bounded best-effort scheduling
  candidate when quota precision is unavailable. `allow_estimated_quota: true`
  separately accepts estimates for that planning decision. Neither fabricates a
  remaining balance, savings figure, free billing route or dispatch permit.
- A later unknown report cannot erase observed exhaustion. The latest numeric
  zero in each owner/provider lane remains a wait until a newer numeric report
  supersedes it or its reported reset passes. A reset never invents a full balance.
  Independent source/window conflicts remain visible and conservative.
- `seconds_to_reported_reset` is simple arithmetic on fresh owner/provider-reported
  timestamps; unknown and estimated dates do not become a precise expiration claim.
  Value priority is an owner declaration for the future dispatcher, not an
  inferred success probability or automatic architecture-plan promotion.
- Any held Build capacity, PREPARED/RUNNING Ask, ended goal or already-started
  work waits for inspection. The policy reserves one of two worker slots for
  foreground work and caps future background concurrency at one. This component
  does not reserve a slot or create a lease.

Billing is a separate required report. A private policy may include an explicit
owner-reported setting observation, with `reported_by`, matching `account_ref`,
`observed_at`, `fresh_for_seconds` (at most3600) and `usage_credits_enabled`.
Do not populate it by assumption or by reading a token/cost estimate. Missing,
enabled, future or stale reports wait. A fresh disabled report is labeled
OWNER_REPORTED_NOT_PROVIDER_VERIFIED, not live billing proof.

Provider documentation explains that usage credits can continue beyond included
usage and can be disabled in account settings. A CLI dollar cap is a client-side
estimate that can be exceeded; it is not proof of zero additional billing.
Sources: [Anthropic usage-credit documentation](https://support.claude.com/en/articles/12429409-manage-usage-credits-for-paid-claude-plans),
[Claude Code CLI budget reference](https://code.claude.com/docs/en/cli-reference).
These public docs were checked2026-10-21; this implementation does not read or
change an actual account's billing settings.

Every view retains `execution_authority: NONE`, runtime/no-extra-spend runtime
qualification NOT_ASSESSED and model identity UNKNOWN where not independently
recorded. `scheduling_candidate: true` describes the declared constraints only.
It cannot be submitted as a lease, OS certificate, billing proof or model permission.
Actual authenticated account/profile binding, one-job dispatch/reservations,
foreground preemption, route-limit reconciliation and live no-spill evidence
remain the next S5/S7 work. No external request is launched by these commands.

[Source-bound component checks](../../evidence/background-queue-2026-10-21/report.json)
cover actual PG/CLI/private files, exact review/replay/race/rollback, owner scope,
reported40percent, overlapping reserves, explicit unknown best effort, exhaustion
across null reports, withdrawal and a real held lease with zero native launches.
Quota/billing/capacity values are labeled synthetic fixtures, not provider/host
qualification. This is partial AOS-012-S5; full TC06/07/10 and G3 remain open.
