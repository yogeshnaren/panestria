# Local repair draft from canonical stopped Build work

Existing finite revisions required the owner to hand-author replacement proposal
JSON; the local planner only drafted from supplied initial files. This connects
those paths while retaining exact owner review and the authoritative revision
service. It is partial AOS-025-S3/X10 delivery, not a new task state machine.

`LocalBuildRepair` reads the current accepted parent, immutable original contract
and inventory, protected progress/check observations, physical return proof,
latest family version and cumulative remaining wall envelope in one repeatable
read transaction. Current policy is revalidated through PlanStore. Unknown/held
work, unconfirmed evidence, uncertain effects, non-stopped tasks, superseded
parents, non-PUBLIC/nonzero-cash authority and exhausted versions/time are refused
before inference. Two repeated protected failed-tree fingerprints stop this path
for owner review. No claim or state is changed by this observation.

The transaction ends before the single explicitly requested local-model call.
The existing compiler accepts a typed repair context, reduces editing/final
wall allocation to the remaining original envelope and retains all original
checks/paths/authority. The prompt contains compact task/check failures; full
binding hashes/event cursor are saved privately. Existing context/output limits,
CPU admission, cache/runtime isolation and generation receipts remain in force.
The supplied publication guard rereads the same source after generation; any
basis change prevents proposal publication while retaining the response/journal.
No database lock is held during model work and no inference is implicitly retried.

A valid result is still NOT_STAGED/PROPOSAL_ONLY. The owner separately invokes
PlanRevisionService, which independently enforces its original proof/budget/
version/task/effect guards and exact consent. Its canonical transaction remains
authoritative; the new observation is a conservative proposal prefilter, not a
replacement permit or durable second store. A trusted callback cannot confer
execution authority. The explicit manual revision path remains unchanged.

The command is bounded per deliberate invocation/output directory. It does not
install an autonomous repair controller or claim persistent total planner-turn
accounting/repair-quality qualification. Those broader S3/S4/S5 obligations and
source/runtime/restart/release checks remain pending. No graph dependency is
added without an actual need for plan/review cycles.

[Runbook](../testing/LOCAL_BUILD_REPAIR.md) and
[source-bound evidence](../../evidence/local-build-repair-2026-10-21/report.json)
cover the actual canonical/CLI journey with explicit model/native fixtures,
remaining-budget/source-change denials and a real repeated failed tree stopping
before inference. No live provider turn or new model was used.
