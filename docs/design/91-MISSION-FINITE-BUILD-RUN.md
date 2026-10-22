# Mission Control finite foreground Build

An accepted plan creates tasks, but previously could only be executed through
the terminal. The explicit `mission-control serve --build-run PRIVATE_CONFIG`
mode connects that exact plan to `NativePlanRunner` and protected final review.
It does not enable the background queue, timers, paid API calls or final merge.

## Durable boundary

The existing canonical Postgres `task_event` ledger retains one request per plan,
one controller claim and one controller return. All writes use the project lock
and caller-owned transactions. There is no second task database or in-memory
completion authority. Closed request/return models bind owner/project/goal/plan,
exact plan hash, original nonce and the private operator configuration hash.

1. Same-origin session/CSRF and current PUBLIC plan/policy checks fence request
   recording, including reauthentication inside the committing transaction.
2. Only an acknowledged request commit can wake an in-process finite controller.
   GET, staging, plan acceptance, startup and polling never wake it.
3. The controller commits its unique claim before constructing/invoking the
   native runner. A lost claim acknowledgment cannot dispatch. An unreturned
   browser-controller claim blocks another browser controller in the project.
4. The existing runner rechecks current source/runtime certificates, pinned
   adapter/inventory, protected Git base, policy, capacity/storage and canonical
   task admission. Its original attempt budgets, scopes and final verifier apply.
5. The return fact describes the Python controller, not physical worker stop,
   released capacity, check PASS or merged output. Missing return remains
   `CLAIMED_UNCONFIRMED`; it is never inferred from thread death or timeout.

Exact request replay preserves its nonce/hash and original 90-second *start
admission* deadline. It can explicitly wake only a still-unclaimed request.
Claimed/returned requests cannot run twice; another nonce cannot bypass this.
Already attempted plans use existing operator inspection/reconciliation and
explicit terminal workflows, not browser automatic adoption/resume. A stalled
claimed browser intent has no automatic release/reconciliation shortcut.

## Withdrawal, observation and limits

Exact cancellation uses existing `PlanLifecycle.cancel`, with fleet→project
lock ordering and same-transaction session fencing. It remains available after
policy revocation, commits before signalling the local runner, and preserves
unknown physical claims. Browser reload/logout does not cancel or repeat an
accepted finite action. Server shutdown signals/withdraws its active plan; a
failed withdrawal or process crash leaves canonical uncertainty, without cleanup.

The run view exposes bounded metadata, not native output, credentials or local
paths. Explicitly enabled storage observations are committed before new claims;
the browser receives decision/warning codes and byte observations without
filesystem paths. A notification failure makes the existing runner defer.
No Docker/Timeshift scan, driver/backup change, deletion or resource scheduler is
introduced. Polling performs no provider, credential, certificate or hardware
probe. Distinct cookie/HMAC purpose binds this mode to its configuration hash.

The run mode includes exact plan intake/acceptance and existing protected PUBLIC
diff/check/consent display. A separate checkbox authorizes each action. Final
merge still requires the existing exact owner CLI path. Other modes gain no run
route or execution authority. Current source/runtime qualification is never
inferred from a staged inventory or this component's fixture checks.

## Validation boundary

Connected tests use actual disposable Postgres, Git, scoped MCP, Docker verifier,
HTTP, CLI pairing and Chromium. Native inference/authentication, runtime
certificates and hardware capacity are explicitly non-live fixtures. Commit-ack
and response-loss injections are labelled. Expiry uses a preparation-only clock
fixture, not claimed elapsed operational time. Real disk capacity is observed
with a synthetic owner reserve threshold. These checks cannot establish live
Claude qualification, all of AOS-028 or any cumulative release gate.
