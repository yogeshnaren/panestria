# 0014: Pace background work toward a reported quota reset

Status: proposed (2026-10-28) for owner confirmation in PR review.

## Context

MVP-X11 asks the background queue to raise urgency as a reported reset approaches. The
owner's example: 40% of the allowance remains and it resets tomorrow. Today the queue
applies a static reserve (20% by default), reports `seconds_to_reported_reset`, and
orders by a tiebreak (`kernel/background.py`, `kernel/background_run.py`). There is no
pacing (drift D5, finding AI-P2e).

## Decision

**Eligibility.** A background job is eligible when its lane has a fresh observation and either:
- `remaining - reserve >= projected_regular_use(hours_to_reset)`, or
- `hours_to_reset <= urgency_window`, as long as the reserve stays intact.

`projected_regular_use` comes from the owner's recorded foreground usage. With no history it falls back to the owner-configured estimate.

**Observation handling.**

| Observation | Treatment |
|---|---|
| UNKNOWN confidence | Never treated as plenty. Bounded authorized work only, per AGENTS.md. |
| Fresher than 6 hours | Required by default for background use. |
| Clock skew up to ±5 s | Tolerated instead of hard-failing. |
| Owner-reported vs provider-reported | Kept distinct with additive confidence values `OWNER_REPORTED` and `PROVIDER_REPORTED`; legacy `REPORTED` stays readable. |

**Visibility.** Each decision is shown in the queue's `waiting_reasons`, and the policy version is incremented.

## Consequences

- Property tests: UNKNOWN never enables unbounded work, and eligibility is monotone in
  time-to-reset.
- The owner can see why a job waits, with no hidden spillover into paid usage.

## Implementation notes (2026-10-28, plan item 1.8)

Recorded where the first implementation narrows this proposal; the decision text above is unchanged.

- **Fixed bounds, not policy fields.** `kernel/pacing.py` sets the 6-hour age cap, a one-hour urgency window and a 10-minute minimum interval for rate evidence. Adding fields to `BackgroundWorkPolicy` would change the digest of every stored policy. Making these owner-configurable needs a new policy schema version.
- **Projected regular use.** The rate comes from the two latest numeric reports in the same lane, window, unit and reset period. With no such pair, nothing is projected and the static reserve still applies. There is no owner-configured estimate yet.
- **No clock-skew tolerance.** The quota ledger requires `observed_at <= created_at`, so a future-dated report is refused at recording. An existing invariant (`test_a_server_clock_rollback_does_not_make_an_observation_new_again`) deliberately treats a server clock rollback as STALE. The proposed ±5 s tolerance would weaken that, so it is not applied.
- **Confidence values unchanged.** `QuotaView.confidence` keeps `REPORTED`. Each observation's `source` already separates `OWNER_REPORTED` from `PROVIDER_REPORTED`, and renaming the view value would break existing readers.
- **New waiting reasons:** `pacing_projected_regular_use_before_reset` and `quota_observation_older_than_background_limit`.
