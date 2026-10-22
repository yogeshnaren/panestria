# Explicit PUBLIC Delegate staging input

Add an opt-in `mission-control serve --research-intake PRIVATE_JSON` mode with a
separate session purpose. The private file pins an existing owner-selected PUBLIC
GoalContract template, immutable ResearchLimits and an existing private CAS root.
The activity settings supply owner/project/port/token. Refuse combined Ask/Build
review modes and mismatched scopes. No search settings, certificate or provider
is required merely to stage a question; none is fabricated or provisioned.

Display the exact frozen contract/bounds and their canonical digest before a
PUBLIC-only question is confirmed. Each manual operation gets a fresh goal UUID;
derive existing research task/request IDs and the idempotency key from that UUID.
The client cannot widen template capabilities, budgets or required checks. Only
goal ID varies. Preserve explicit public intent, canonical policy fencing and all
existing checks; the browser never completes a task or grants semantic support.

Reuse `stage_question` and `ResearchSubmissionService`, allowing a caller-owned
transaction. The API locks the project and reauthenticates the session/CSRF on
that same connection before CAS/staging and again before commit. This orders
policy change/session revocation with mutation. A late rollback can leave private
unreferenced immutable bytes, never a committed request pointing at absent bytes.
No goal activation, network, model, worker, acceptance verdict or effect dispatch.

Responses show canonical receipt/goal/task states and retained question via the
existing verified brief inspector. After an uncertain response, only GET recovery
for the same goal is available; no automatic POST retry. Default observer routes
remain absent. Typed production UI uses inert text and memory-only state; full
Delegate execution/support and real search/runtime qualification remain pending.

Check actual browser/HTTP/PG/CAS/CLI pairing, exact contract/bounds, no execution,
replay/ambiguity, stale policy, foreign scope, missing public intent and CSRF.
No live search, inference, fabricated certificate or owner trial is involved.
