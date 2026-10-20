# Stage a PUBLIC Build plan without SQL

The existing preflight checks three private files: a goal contract, inventory and
proposal. This command additionally creates the canonical goal, its exact
acceptance-check rows and the frozen proposal in one transaction. It requires an
existing owner/project and current policy; it does not create policy, credentials,
leases, accepted tasks or a model call.

Prepare the files as described in [Build preflight](BUILD_PLAN_PREFLIGHT.md). Use a
new goal UUID, contract version1, PUBLIC classification and zero API cash. Node
budgets/check/path/capability limits must fit that exact goal. Inventory hashes are
declarations; current native/OS compatibility and actual source/capacity still need
validation before execution. Keep the private files out of Git.

```bash
panestria plan validate OWNER_UUID PROJECT_UUID --contract /absolute/private/goal.json --inventory /absolute/private/inventory.json --proposal /absolute/private/plan.json
panestria plan stage OWNER_UUID PROJECT_UUID --contract /absolute/private/goal.json --inventory /absolute/private/inventory.json --proposal /absolute/private/plan.json --idempotency-key YOUR_UNIQUE_STAGE_KEY
panestria plan inspect OWNER_UUID PROJECT_UUID PLAN_UUID --output /absolute/private/review.json
panestria plan accept OWNER_UUID PROJECT_UUID PLAN_UUID EFFECT_DIGEST --accept-plan
```

The database comes from `PANESTRIA_DATABASE_URL`. Stage returns plan/goal IDs,
proposal SHA, the exact pending consent/effect digest, state PROPOSED and execution
authority NONE. Review the private frozen proposal, contract/checks, scope and
budget before separately accepting its exact digest. Consent lasts15minutes; a
stale review cannot grant authority. Acceptance creates CREATED canonical tasks;
it still does not launch workers or approve their eventual merge.

Repeating the identical stage key reuses the same goal/checks/proposal and does not
renew consent or dispatch work. Replaying after acceptance reports ACCEPTED with
no additional tasks/attempts. Changes to that key's contract, proposal, inventory
or retained acceptance rows are refused. Revisions/repair remain a separate planned
path; this command does not overwrite original contracts or evidence.

A rollback leaves no partial new goal, checks or proposal. Read [scheduler commands](PLAN_SCHEDULER.md)
for readiness/claims, [final-tree review](FINAL_TREE_INTEGRATION.md) for exact combined
checks/approval, and [plan cancellation](PLAN_LIFECYCLE.md) to withdraw all tasks.
A first reservation marks the staged goal ACTIVE but has dispatch authority NONE.
The [native fork/join driver](NATIVE_PLAN_EXECUTION.md) provides a separately qualified
PUBLIC two-worker path after explicit acceptance/run. Staging itself is an owner
setup operation and supplies no runtime qualification or release-gate pass.
