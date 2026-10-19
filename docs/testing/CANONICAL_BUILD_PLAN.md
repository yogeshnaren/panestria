# Canonical Build plan and handoff storage

This component retains validated proposals, exact owner consent, canonical task
references and source-bound handoffs in the same PostgreSQL transaction as their
events. It does not launch a worker or complete/merge a task. Initial versions are
one per goal; direct model proposal, bounded revisions/repair and two-worker
admission remain AOS-025/026 integration work.

Use a separate trial database migrated to `0033_canonical_plans` and explicitly
configured `PANESTRIA_DATABASE_URL`. No database is selected or migrated by these
commands. Prepare an existing canonical goal/contract under its current project
policy. Use private JSON files for the typed proposal and declared inventory,
following [the pure DAG preflight](BUILD_PLAN_PREFLIGHT.md).

```bash
panestria plan prepare OWNER_UUID PROJECT_UUID --proposal /private/proposal.json --inventory /private/inventory.json
panestria plan inspect OWNER_UUID PROJECT_UUID PLAN_UUID --output /private/new-plan-review.json
```

`prepare` binds the canonical latest contract, owner/project, declared inventory,
DAG/checks/budget, current policy and a 15-minute UTC consent expiry. It returns the
plan ID and exact `effect_digest`. It creates no task or grant. Lost replies replay
the exact proposal; a changed proposal is refused until bounded revision support
is implemented. Inspect the retained private review before accepting its digest:

```bash
panestria plan accept OWNER_UUID PROJECT_UUID PLAN_UUID EFFECT_DIGEST --accept-plan
```

The separate explicit confirmation creates immutable membership plus canonical
CREATED task rows and dependencies atomically. Duplicate/concurrent confirmation
creates one acceptance/event; rollback leaves no accepted tasks or phantom event.
The receipt has execution authority NONE. Created nodes still need independent
admission; no dispatcher is provided by this component. Binary/profile hashes in
an inventory remain declared planning context, not current runtime certificates.

Once an admitted node has actual current canonical Build evidence, a controller
or owner can retain its handoff with a private submission file:

```bash
panestria plan handoff OWNER_UUID PROJECT_UUID --submission /private/handoff.json --evidence-store /private/existing-evidence-root
panestria plan inspect-handoff OWNER_UUID PROJECT_UUID HANDOFF_UUID --evidence-store /private/existing-evidence-root --output /private/new-handoff-review.json
```

The submission contains `handoff_id`, `plan_id`, `task_id`, current
`expected_task_version`, `evidence_sha256`, optional member `next_tasks` and a note
of at most2048UTF-8 bytes. The store derives candidate commit/tree/snapshot,
contract/plan/inventory hashes and attempt/epoch from current protected evidence.
It checks complete required PASS reports and canonical source/task membership;
a worker's prose cannot supply those facts. The actual adapter name stays
separate from the declared worker inventory, with runtime qualification
NOT_ASSESSED. Separate admission/runtime qualification is still required.

Notes are UNTRUSTED_NOTE, next-task references are advisory and completion
authority is NONE. Identical replay adds no event; changed payload, actor,
contract/policy, task fence or candidate proof refuses. Inspection revalidates
current source rather than presenting stale context as current. Immutable audit
bytes are retained even when a current-source read is refused.

Plan acceptance is separate from existing exact merge approval. Nothing in these
commands chooses a provider, sends model requests, changes privacy/tools/budgets,
prunes storage or deletes retained history. Populated plan audit blocks lossy
schema downgrade; empty downgrade/reapply is separately checked. Migrate/restore
only the explicitly chosen trial database before production qualification.

The controller PG/Git/CAS fixtures exercise storage and consent. Their reports are
synthetic controller fixtures, not native-worker/OS-verifier qualification or a
full AOS-025-TC02/G3 pass. Model-generated plans, parent revisions, full runtime
qualification and user-facing scheduling remain pending.
