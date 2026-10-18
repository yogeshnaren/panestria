# Owner question submission without execution

This task connects a new owner-supplied PUBLIC question to the canonical
goal/task/request store and existing private retained-evidence inspection. It
depends on the research brief and shared-runtime tasks; it does not activate a
task, grant public-web permission, plan queries, fetch sources or declare support.

## Admission and identities

The local administrative command accepts a canonical GoalContract, a private
UTF-8 question file (1–65,536 bytes), ResearchLimits, a private CAS root and an
explicit `--public-question` declaration. Use an existing configured owner/project
and the exact current project policy reference. It never initializes or updates
that policy, credentials or an owner service.

`execution/research_submission.py::stage_question` validates owner/project and
PUBLIC intent, then derives stable UUIDv5 task/request/artifact IDs from the
contract's canonical UUIDv4 goal ID and versioned purpose names. These identities
are opaque links, not authority. It acknowledges immutable question bytes in the
existing owner/project ResearchBlobStore before opening the DB transaction.

`kernel/research_submission.py::ResearchSubmissionService.stage` takes the caller's
transaction and locks project → goal idempotency → request/audit/event. It validates
scope, current policy and the unchanged canonical contract loader. Unadmitted R2
citation/rubric runners remain refused. It calls GoalService.submit, inserts the
task, question artifact and unchanged acceptance specifications, prepares the
bounded research request and appends events in the same transaction. **Goal and
task stay CREATED**, with no lease, activation, verdict or outward effect.

## Replay, crash and privacy behavior

The same scoped key/contract/question/limits returns the original stable receipt
with `replayed=true` and no duplicate rows/events. It cannot attach another
workflow's goal, change the question or silently widen the limits. Concurrent
submissions serialize on the existing project/idempotency locks. A committed
transaction followed by lost acknowledgement is safely replayed without starting
execution. Any exception before commit rolls back all new DB rows and events.

The CAS and database are not one atomic filesystem transaction. A rollback can
leave a durable, unreferenced private question blob. Do not delete or rewrite it
as automatic compensation; retention/cleanup is a separate explicit operation.
The DB acknowledgement never precedes the question's acknowledged CAS write.

Terminal output contains IDs, a request hash, replay state and
`STAGED_NO_EXECUTION`; it omits the question, file paths, DSN and raw exception.
Questions, including embedded instructions, remain data in the protected CAS.
The command reads bounded private files and makes no model, search, fetch or
reader call. This is local DB administration, not a remote-authentication claim.

## Inspection and next boundary

The existing `research inspect` command can immediately export the new staged
question/limits-linked request as private inert HTML/JSON with zero claims and
NOT_ASSESSED semantics. A staged task cannot acquire a lease from CREATED.

Execution must be a later explicit operation that rechecks current joint runtime
qualification, reviewed web policy, contract capability/egress and budgets before
activation. If policy changes, an old pinned contract is not upgraded silently;
stage a new goal against the reviewed new policy. Current offline-only staging
examples cannot become public-web grants. Planner, collection/error presentation,
semantic support, adversarial/live Delegate and G2 remain pending. No original
gate, historical evidence or acceptance vocabulary changes.
