# Durable launch intent for the registered-check controller

Prerequisite PR91 adds exact launch references and truthful reconciliation but
retains the reference in memory. Record that opaque reference before Docker
create on the existing PostgreSQL invocation ledger. Intent and event share the
caller transaction; no Docker operation occurs inside it. A lost commit reply
must prevent create, and an existing intent must never mint another permit.

Add a strict metadata contract and immutable one-to-one invocation launch table,
with binding, scope, runtime slot, launch nonce, profile and image hashes. No
workspace path, credential, prompt or second task store is needed. Recording
requires current owner/project/policy/lease/contract and a CLAIMED unexpired
native-tool invocation. The global event lock remains last. Schema constraints
preserve the exact invocation/binding/JSON identity; populated downgrade refuses.

A trusted DockerSandbox callback commits the intent before create. The actual
RegisteredCheckController uses an authority-bound runner factory, including its
policy/certificate checks. Uncertain intent admission never creates a container.
Historical scoped read/reconciliation after expiry/revocation may remove the
stored exact owned resource but cannot start work, mark task/check/approval done,
restore authority or retry an invocation. Retain bounded historical observations.

Test actual PostgreSQL transactions/races/restore and owned Docker/process death,
not only JSON callbacks. Kill the controller around intent, create and process
start; reconstruct it and recover exact resources while preserving unrelated
fixtures. An execution marker is not verification or owner acceptance. Keep
unknown effects fenced rather than guessing they did not occur.

This is not exactly-once external execution. Fresh one-use claim/intent checks
must not be replaced by a cached DBOS result that permits another launch during
replay. Future workflow integration must reconcile uncertain dispatch, and all
native auth/proxy/MCP, grant/lease/budget boundaries and full G1/G2/G3 proof remain
required. Preserve prior source-bound observations; never relabel them after the
backend/schema change. Stop before the R3 owner-trial acceptance checkpoint.
