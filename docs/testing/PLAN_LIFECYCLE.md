# Stop a canonical plan and inspect capacity holds

The accepted plan's proposal hash is its frozen `proposal.sha256()` from the
private plan inspection. It is different from the consent/effect digest.

```bash
panestria plan cancel OWNER_UUID PROJECT_UUID PLAN_UUID PROPOSAL_SHA256
panestria plan claims OWNER_UUID PROJECT_UUID PLAN_UUID
```

This withdrawal command needs the existing database environment and owner/project
scope, without a model, network, live certificate or inference call. It remains
available after policy revocation. The existing Build review terminal/`build cancel`
also route accepted plans to this service. A separate legacy one-worker goal keeps
its existing behavior.

Cancellation fences **all tasks in the goal**, including siblings, dependencies
and final integration, under the same Postgres transaction and event. It does not
undo already completed work or applied external effects. No new dispatch may use
the cancelled attempts. Exact concurrent/repeated requests do not duplicate the
cancellation/release audit. Rollback retains both previous state and capacity.

If durable records show no invocation/effect was claimed, the task can become
CANCELLED and the reservation gets an immutable NO_DISPATCH release proof. If a
process/effect was claimed, returned ambiguously or remains unknown, the task stays
CANCELLING and capacity remains held. CANCEL_REQUESTED reports those holds; it is
not a termination confirmation. Even expired/failed attempts are not automatically
assumed stopped. This component does not force-release, kill unrelated processes,
prune containers/files or invent a successful reconciliation. Qualified physical
termination/recovery for uncertain processes remains executor work.

After an exact verified final merge completes, the existing owner approval path
now separately records a VERIFIED_FINAL release using its immutable effect receipt,
full-tree evidence and original plan/task/epoch. A crash before that second commit
can leave a safe hold. Reconcile it explicitly with its actual identifiers:

```bash
panestria plan release-final OWNER_UUID PROJECT_UUID PLAN_UUID FINAL_TASK_UUID EVIDENCE_SHA256 EFFECT_UUID --evidence-store /absolute/private/build-evidence
```

This only acknowledges a past completed and confirmed merge, including after a
later policy change. It never authorizes another merge or provider action. A wrong
plan, non-final task, unconfirmed effect/evidence or mismatched epoch is refused.
Repeating the exact proof is harmless. Historical claims/handoffs are preserved;
new immutable release records determine whether a claim still occupies capacity.
Migration0035 refuses populated downgrade; observed schema snapshots and Ask
readiness track the new head. Owner databases are not automatically migrated.

Focused checks use real disposable Postgres, actual dump/restore, protected Git
and Docker verification. Native/capacity identities remain controller fixtures;
no new provider, runtime, release gate or owner trial is qualified by these cases.
