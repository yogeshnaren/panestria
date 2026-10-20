# Canonical plan queue and bounded CPU admission

This delivers persistent ready-node reservation and independently verified node
completion. It does not launch a model/process or qualify a two-worker runtime.
Use an already migrated disposable/review configuration and an accepted executable
plan from [canonical storage](CANONICAL_BUILD_PLAN.md). Do not recreate owner data.

```bash
panestria plan claims OWNER_UUID PROJECT_UUID PLAN_UUID
panestria plan queue OWNER_UUID PROJECT_UUID PLAN_UUID --evidence-store /absolute/private/build-evidence
panestria plan claim OWNER_UUID PROJECT_UUID PLAN_UUID --evidence-store /absolute/private/build-evidence --skills-archive /absolute/path/agentos-skills-v0.1.0.zip
panestria plan complete-node OWNER_UUID PROJECT_UUID PLAN_UUID HANDOFF_UUID --evidence-store /absolute/private/build-evidence
```

`PANESTRIA_DATABASE_URL` supplies the existing database; no command migrates it.
Claims shows historical attempt IDs, capacity holds, expiry and unresolved invocations, including after policy changes. Queue shows ready/wait reasons. Claim runs the pinned read-only CPU hardware probe,
then reserves one ready node atomically with its fenced lease and event. RESERVED
means capacity held, **dispatch authority NONE**. Do not repeatedly claim to retry
a lost reply: inspect canonical tasks/claims first. Actual qualified execution,
context export consent, adapter identity and no-extra-spend eligibility are still
required at dispatch. No model download, provider fallback or API purchase occurs.
Unknown quota is recorded as unknown and does not invent a zero balance or price.
Only zero API cash, existing bounded CPU edit/test capabilities are admitted here.

Across accepted plans in this database, no more than two unresolved claims exist.
Accepted per-plan and per-worker limits can lower that cap. Independent controllers
serialize through a Postgres transaction lock. Dependencies require current,
protected verifier evidence and a retained canonical handoff/completion, rather
than a worker's done message or a task-state edit. Same-plan overlapping literal
paths wait. No command overwrites another worker's workspace.

The fixed CPU reservation conservatively counts every unresolved claim again
against available RAM: 2 CPU cores, 2.5GiB RAM and 1GiB disk each, plus a foreground
reserve of 2 cores/2GiB RAM/2GiB disk. The pinned observation must be actual, timezone
aware and at most 30 seconds old, on AC power and not hot. GPU/local-model jobs
need separate qualified admission; these are estimates, not OS partition guarantees.
Existing unrelated programs are reflected in current free capacity; this ledger
alone does not enforce an OS process ceiling for legacy non-plan launch paths.

Expiry, FAILED/CANCELLED state and ambiguous invocations retain their reservation.
They do not prove a process stopped. This first release has no force-release,
cleanup, automatic retry or reconciliation bypass. Completion accepts only a
current successful intermediate handoff with returned invocations; it atomically
marks that node COMPLETED, releases its claim and records the proof. Repeating
that exact completion is harmless. It does not complete the goal, request a merge
or bypass the final task's full checks/owner approval. Final-task resource release
and failed/unknown-process reconciliation remain subsequent executor work.

Focused checks use real disposable Postgres databases, Git candidates and protected
CAS/path verifier results. Capacity values and worker identities are explicitly
controller fixtures. They do not establish hardware, vendor, OS or release gate
qualification. Migration 0034 preserves the audit and refuses populated downgrade.
