# Native authority observations without task-row contention

The failed platform run on PR156 stopped a worker before foreground yielding.
A local ordered reproduction also stopped native workers. PostgreSQL reported
statement timeout while taking `FOR UPDATE` on `task`; lock-holder capture found
another monitor at COMMIT, still holding its task lock after 0.754 seconds.
The original CI result did not include lock metadata, so this diagnoses the
reproduced mechanism rather than claiming every historical stop has this cause.

Periodic checks were using the same locking transaction as dispatch. Tuple
locking can require WAL/commit work even when no application column changes.
The monitors could therefore delay each other until the existing 300ms database
or 500ms gateway limit failed closed. Those bounds are unchanged.

`InvocationService.observe` now requires a read-only repeatable-read transaction
and checks the current scoped task, epoch, attempt, contract, policy reference,
invocation binding, state and expiries in one nonlocking snapshot query. Each
periodic native/edit observation opens a fresh transaction. It also rechecks the
current certificate, declared edit/export policy and runtime/claim where required.
An observation is not a claim, permit, reusable authorization or receipt.

Claim, disclosure, before-start, returned receipt and verifier publication retain
their existing locked authority checks. Revocation/cancellation after a snapshot
is detected by the next fresh observation and by those locked boundaries.
Expiry uses the actual database clock. Missing, invalid or stalled observations
still stop work. No retry, provider fallback or capacity release is added.

Only the edit authority explicitly opts into the gateway observation protocol.
Other durable/custom authorities retain their existing `check` implementations;
inheriting a generic base must not bypass a subclass's additional policy checks.

The connected regression holds a real locked check open while an observation
completes with a 150ms statement limit, then commits cancellation without waiting
on the observer. Both fresh observation and locked dispatch reject that state.
The prior expiry/epoch/contract matrix now also exercises observation rejection.
[Source-bound evidence](../../evidence/authority-observation-2026-10-21/report.json)
records 82 affected component cases passing, nine live cases excluded, original
failed diagnostics and unchanged limits. Actual runtime qualification and
cumulative release gates remain separate; no live provider was called.
