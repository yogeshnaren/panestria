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

## Implemented boundary and validation

The registered-check controller now uses the authority-bound runner factory. Its
callback validates the actual profile: wall time may be reduced to the remaining
deadline, and all other resource, identity, image and permission fields must stay
exact. A lost commit acknowledgment creates no container. Current authority is
checked again before startup. Historical cleanup changes a still-CLAIMED
invocation to UNKNOWN and appends its observation atomically; existing UNKNOWN
or RETURNED receipts remain intact. No task/check/approval is completed.

At clean `ec9a43f`, 170 focused checks pass (46 new). Six actual controller SIGKILL
cases cover intent/create/running windows with and without lease release; two
actual admission faults and actual migration/dump/restore checks pass. The actual
head28 schema snapshot has1078 lines. Evidence and earlier profile/API failures
are retained in `evidence/durable-sandbox-launch-2026-10-16`. Direct crash fixtures
use a fixed synthetic Python script; registered-controller integration is tested
separately. This does not certify native auth or all other worker/verifier/control
stage lifecycles or provide autonomous liveness/sweeping policy.

## DBOS documentation check (2026-10-16)

DBOS documents atomic datasource work plus outcome tracking, with stored results
replayed after interruption. Completed steps are retained, while interrupted
external actions can require retry or reconciliation. These guarantees support
same-database state/events; they do not make Docker effects exactly once. See
[Transactions and Datasources](https://docs.dbos.dev/python/tutorials/transaction-tutorial),
[workflow guarantees](https://docs.dbos.dev/python/tutorials/workflow-tutorial) and
[the outbox example](https://docs.dbos.dev/python/examples/outbox).

This controller currently uses fresh caller-owned PostgreSQL transactions for
one-use claim/intent checks. Full workflow integration must preserve that fence
and reconcile unknown dispatch rather than treating a cached transaction result
as a fresh launch permit. Existing accepted R0 datasource/state/event evidence
is preserved; this component does not reopen or replace that acceptance.
