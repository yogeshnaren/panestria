# Historical returned Build release boundary

AOS-026/025 recovery needs to distinguish a physically finished failed call from
unknown work before finite repair can reserve another slot. Use the existing
immutable `build_claim_release` ledger with additive reason VERIFIED_RETURN. No
new task state/store, process watcher, native replay or provider route is added.

The owner-invoked service holds fleet→project→goal→task/claim/attempt locks using
PlanLifecycle's historical owner scope. Original plan membership/contract and
current competing attempts/effects remain fenced. Canonical invocation JSON and
hash, owner/project/task/attempt/epoch, contract/policy and content-addressed report
bytes must match. Only returned receipts or fenced never-claimed PREPARED entries
are eligible; CLAIMED and UNKNOWN are not repaired by assertion.

The native role requires the known Bash profile, ignored hostile customization
and terminated process receipt, bound to the exact disclosed context/scope. A
noncandidate native response takes the existing stop-before-verifier branch. A
candidate response can precede independent checks, so it additionally requires a
published protected verifier bundle, exact scoped checks/definitions and known
stopped-cleaned/prelaunch check reasons. This avoids freeing a cancelled candidate
while its separate verifier may still run. A candidate without this proof stays
held. Passed verifier evidence can support withdrawal accounting but never gives
this service completion/merge authority.

The final role requires its separately tracked build-integration receipt, scope/
binding, physical-return status and exact integration input/attempt/epoch/report
references. Unknown cleanup and unrecognized profiles remain unavailable. No
read/write/delete/grant/spend action is inferred from a quota value or release.
No dispatched side effect or other active attempt may compete with the proof.

Commit proof, permitted cancellation state transition and event in the caller's
same PostgreSQL transaction. Retain original claim rows and handoff history.
Historical replay checks the already committed immutable proof rather than
starting work; revocation remains effective for all future actions. Failed task
states and prior successful verifier observations remain honest. The owner must
separately choose cancellation or a bounded new plan; no automatic retry follows.

Migration0036 only extends the release reason check. Actual disposable PostgreSQL
fingerprints update the schema snapshots/readiness head. Populated VERIFIED_RETURN
downgrade refuses, and actual backup/restore must retain proofs, hold accounting
and replay. Report/CAS retention remains part of the backup, not plaintext input
in ordinary telemetry or permission to export training examples.

This slice leaves true unknown native/OS cleanup and cancelled candidates without
verifier return proof held for later qualified reconciliation. General DAG,
finite canonical revisions/progress/repair and cumulative R3 qualification remain
separate requirements. Synthetic transport receipts in component tests are not
live provider evidence or proof of generic runtime conformance.
