# Stopped native-worker diagnostics

Two-worker CI runs40012690070 attempts1/2 stopped before final review. The original
truncated assertions did not preserve enough detail to identify a cause. Those
failures remain failures; a subsequent local pass does not explain them.

The controller now returns a closed, redacted cause when native execution,
monitoring, scoped gateway authority or a worker future fails. Database lock,
statement, deadlock, serialization and availability failures are distinct.
Other authority denials and unconfirmed execution remain conservative categories.
SQL text, exception messages, paths, account data and native output are omitted.
The existing CI journeys retain complete synthetic worker results in JUnit so
future failures can be investigated without guessing from truncated assertions.

The change does not alter status, claim/launch/publication checks, read-only
monitor semantics, timeouts, retries, capacity release or merge authority. A
category is diagnostic metadata, never evidence of physical return or safe retry.
UNKNOWN invocations and held claims remain held; inspect their canonical state
using the existing Build progress/reconciliation commands. Never clear or repeat
work just because its diagnostic suggests a transient error.

If a database category appears, inspect the actual service/resource observation
before choosing a repair. It does not establish Docker/backup ownership or grant
storage deletion, service reset or backup changes. Missing details remain unknown.

[Component evidence](../../evidence/native-worker-diagnostics-2026-10-23/report.json)
records42 affected real disposable PG/Git/MCP/Docker checks, with3 live cases
excluded. Native/account/capacity/certificates and injected faults are explicit
fixtures. New checks verify private exception text is omitted and uncertain
claims cannot create handoff/approval or release capacity. Existing success,
revocation, cancellation, quota, read-only observation and grant limits remain.
This improves diagnostics; the original intermittent cause remains unresolved
until actual failure evidence identifies it. No live/provider/release pass.
