# 0009: Run Build, Research and Background as DBOS workflows

Status: accepted owner decision (2026-10-28). Implementation pending; no code changes in this record.

## Context

DBOS durable execution currently covers only the synthetic R0 queue
(`execution/dbos_runtime.py`, queue `panestria-synthetic`). MVP Build runs in a daemon
thread inside the API process (`execution/mission_run.py`) and a thread pool for two
workers (`execution/native_plan.py`). A restart leaves capacity claims occupied until
the owner reconciles them (`kernel/scheduler.py` module docstring). Nothing scans
`effect_outbox`, so effects left EXECUTING or UNKNOWN are never discovered (review
findings F-D1 and F-D2).

## Decision

1. Add a separate `panestria worker serve` process with one DBOS configuration and
   these queues. The API process never executes workflows.

   | Queue | Concurrency |
   |---|---|
   | `panestria-build` | 2 |
   | `panestria-research` | 1 |
   | `panestria-background` | 1 |
   | `panestria-synthetic` (R0, kept unchanged) | — |

2. Enqueue each Build plan run in the same PostgreSQL transaction as its capacity claim,
   reusing the admission pattern (`execution/admission.py` `enqueue_in_transaction`).
   Per-node child workflows replace the thread pool.
3. Workflow steps follow these rules:
   - `claim_ready` and `capture_and_verify` are idempotent.
   - `record_launch_intent` durably records intent before any native launch.
   - `launch_native` has `retries_allowed=False`.
   - Approval waits use `DBOS.recv` with a durable timeout.
4. **Recovery rule.** A launch intent without a recorded outcome moves the attempt to
   RECONCILING (`uncertain_native_launch`). Native work is never automatically resumed
   or re-dispatched (AOS-024-TC03).
5. Research stages and Background runs become workflows on their queues. Fetches are
   idempotent by request identity.
6. One effect ledger always writes the outbox row and exposes `list_stuck(now)`.
7. A scheduled sweeper applies only proven-safe transitions: release a lease that
   expired without a launch intent, and mark an intent without outcome RECONCILING.
   Each transition adds a review-inbox notice.
8. Task state changes go through one transition function. A database trigger is
   generated from `contracts.task.ALLOWED_TRANSITIONS`, first in warn mode and then
   enforced.

## Consequences

- Crash-at-every-step tests become possible and are required. The invariants are no lost
  task, no duplicate effect and no stuck RUNNING.
- Operators run a worker service in addition to the API (systemd user unit).
- DBOS system tables become part of backup/restore. Restore applies a fence (bump lease
  epochs, EXECUTING to RECONCILING, hold pending workflows) before resuming.
