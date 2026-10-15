# Database and migration implementation design

[schema-blueprint.sql](schema-blueprint.sql) combines the repaired base tables with scoped constraints and R1–R3 extensions. It is a design blueprint, not an applied or independently syntax-parsed migration: this planning workspace has no PostgreSQL server/parser. Cursor splits it into Alembic revisions and proves them in disposable PostgreSQL before use.

| Revision | Stage | Ownership / objects | Required proof |
|---|---|---|---|
| 0001_kernel | R0 / 002,003,005 | principal/project/goal/immutable contract/task/dependencies/attempt/workflow_link/check/run/artifact/approval/consumption/event/idempotency; synthetic side_effect skeleton, scope FKs and closed states | Clean apply, SQL scope/state/null rejection, immutable body/delete, optimistic race, identity commit order and consistent restore |
| 0002_policy_effects | R1 / 006–010,027a | Harden leases/effects/outbox/budget, policy/trust/action/capability/sandbox/session metadata; retain R0 approval/consumption primitives | Lease/consume/reservation races, response loss and stale-policy denial |
| 0003_memory | R1 / 011,017 | Source/item/revision/use_event/context_pack; FTS, validity/pin/suppression/retention | Scoped recall, supersession, five stages, source/pin and suppression restoration |
| 0004_telemetry | R1/R3 / 012,014,029 | Route/outcome/correction, usage/exposure observations, hardware/runtime metadata | DB-only restart reconstruction, unknown=null, safe trace and exposure separation |
| 0005_research | R2 / 013,019–023 | Request/snapshot/claim/passage/report; immutable raw/text/extractor/byte-offset versions | Wrong scope/hash/offset rejected; incomplete/truncated status preserved |
| 0006_plans_fleet | R3 / 025–030 | Plan/version/task link, workspace/candidate/fleet, gate/trial/review | DAG and candidate membership, final-tree evidence, distinct build/gate/owner acceptance |

DBOS migrations stay DBOS-owned, in the same physical database and separate schema. App schema is panestria. Provision schema/grants with a migration role; runtime gets minimal privileges and no schema mutation. Workers get no DB credentials. SQL blueprint ALTERs assume a new empty schema; when translating existing populated tables use add-nullable→backfill→constraint validation→NOT NULL instead of blind non-null ALTER.

## Transaction responsibilities

create_goal: validate actor/project and idempotency request hash; insert immutable version/task/check rows and consent/admission; if executable enqueue through supported DBOS client in the same caller-owned transaction; append events last; commit once.

transition_task: compare expected row_version/state/lease_epoch, enforce allowed edge/continuation, mutate domain metadata, append events last, let datasource callback result share commit. Zero changed rows is conflict/fenced. Terminal correction is a new audited record, not resurrection.

decide_approval: lock request; authenticate actor, current digest/scope/policy/expiry; one decision with actor/time/event. Preparing the effect separately consumes it atomically into one stable effect/outbox intent. Execution is outside DB; finalize/reconcile in another tracked transaction.

reserve_budget: lock project budget/reservations, compute integer micro-USD settled+reserved, deny overcap. Unknown cost requires conservative bounded policy/approval; not zero. Release/settle once by stable identity. Subscription quota observation is not API cash.

Lock domain rows deterministically before the global event append lock; no domain locks or network work after sequence allocation. Repositories use supplied sessions and never commit independently.

## Service invariants SQL cannot establish alone

Verifier type enum/spec agreement does not prove a command registry ref is reviewed or a runner installed. DAG FKs do not prove acyclicity or same approved plan; validate scoped edges in services. Artifact/check PASS requires current candidate/contract/epoch and finalized hashed bytes, not another run's success. Approval consumption uniqueness does not prove semantic payload/digest/actor/policy freshness. Native effect receipts, OS guards and UTF-8 passage boundaries require actual adapter/verifier tests.

Application reads and background writes all enforce owner/project. Composite FKs cover contract/task/attempt/artifact and research request/source/claim association; remaining semantic scope checks are explicit security fixtures. RLS is optional defense in depth only after a tested identity/session/role model, not an asserted guarantee.

## Immutable data, backup and retention

Contract rows change by new version; approval metadata is once-only. Source snapshots/extraction changes create new versions, enforced by service/repository guards and restricted writes (add immutable triggers if chosen; test them). Evidence blobs are protected and hash-checked on read. Ordinary runtime cannot reset global seq or bypass ordered append.

Backup app and DBOS schemas consistently plus artifact/version manifest before upgrades. Test isolated restore with vendor/remote launches disabled until unfinished effects/identity/policy are reviewed. Recovery cannot blindly repeat UNKNOWN remote effects. Destructive downgrade needs proof; otherwise restore/forward repair. Event retention returns scoped resync snapshot and cursor floor. Suppressed memory remains excluded from new contexts; physical backup/provider erasure timing stays explicit.

## Revision 3 additive storage work

The old numbered design revisions above are prospective logical groups, not the deployed Alembic chain. Inspect actual head and never rewrite applied migrations. Add scoped immutable profile ciphertext/key-reference metadata, audited legacy classification resolution, versioned connection/background policies, quota observations and offline-result/purpose/provenance relations as required by [revision 3](../specification/architecture/05-PERSONAL-PLATFORM-REVISION-3.md). No key material goes in DB/backups/worker settings; restricted profile plaintext must not enter general FTS. Reference/knowledge use and training eligibility are independent fields. Existing task/attempt/event/outbox state remains authoritative; all new rows enforce owner/project scope and tested restore/retention behavior.
