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

A [later four-case closed-cause check](../../evidence/native-worker-diagnostics-2026-10-23/closed-causes-report.json)
adds known authority-code detail while redacting unknown authority text. It
overlaps two earlier cases and remains separately source-bound; the counts are
not pooled. Other malformed/unrecognized errors stay conservatively generic.

The original diagnostic CI40040656545 retained both workers returning
`scoped_gateway_unknown` before final verification; it does not prove a database
error. A [separate gateway-phase observation](../../evidence/native-worker-diagnostics-2026-10-23/gateway-phases-report.json)
now distinguishes observation deadline, watchdog shutdown and sandbox-return
uncertainty using existing state flags. The same bounds/outcomes remain. The
shared fixture records complete results across native-plan journeys. Its57
focused checks and10 excluded live cases remain a separate source cohort.
Root-cause investigation is still open; no changed timeout or retry is introduced.

## Gateway stop causes (November 2026)

Three later CI Build runs ended `STOPPED`: two in `hermeticity (kernel)` and one
in `behavioral (platform)`. Each failing test took 30–32 s, against 2–5 s when
it passed. That matches one scoped Bash call using its whole 30 s script
budget. The exact phase is in each run's JUnit `native_plan_result` property;
those artifacts were not downloaded for this note. On a heavily loaded local
host, the Docker part of one scoped Bash call grew from about 1.2 s to 14–45 s.
Calls then overran the 30 s script budget and the 35 s invocation TTL, and
final checks overran the fixture's 10 s check budget, so final nodes ended
`FAILED`. Stopping is the intended fail-closed result in each case.

Most of those overruns were reported as revocations. After stopping a worker,
the gateway kept probing authority while the worker was reaped. The
invocation's TTL then lapsed, and `invocation_inactive` outranked the
deadline. Now the first stop names the outcome, and no authority probe starts
after a stop. A worker's reason names the gateway outcome:
`scoped_gateway_deadline_exceeded`, `scoped_gateway_authority_revoked` or
`scoped_gateway_cancelled`. Budgets, retries, claims and acceptance are
unchanged.

Runtime versions include a digest of every `src/panestria/**/*.py`. Editing
those files in a checkout while its tests run is a runtime change. Preflight
then refuses with `public_native_plan_not_eligible`, running workers stop with
`native_build_runtime_changed`, and certificate checks report
`certificate_mismatch`. That is the intended refusal, not a load symptom.
