# API, CLI and UI contract through R3

All /v1 routes require local identity except liveness and tightly bounded session pairing. Pydantic schemas are the generated OpenAPI source; browser/CLI never hand-copy enums. Internal services receive ActorContext(owner_id, project_id, capabilities, correlation_id), not user-supplied authorization flags. Unknown fields rejected. Error shape: code, message, correlation_id, retryable; safe diagnostics never contain credentials or private filesystem roots.

| Route / method | Request/response | Release / behavior |
|---|---|---|
| GET /healthz | liveness/version/profile | R0; no secrets or model dependency |
| GET /readyz | DB/executor/degraded reason | R0; bounded probe, not invented health |
| POST /v1/goals | GoalCreate(contract, Idempotency-Key)→202 GoalView | R0; immutable version and scoped admission |
| GET /v1/goals/{id} | GoalView(tasks/effects/current version) | R0; foreign scope 404 |
| POST /v1/goals/{id}/contracts | ContractRevision(expected_version, body) | R0; creates immutable new version, invalidates old approval |
| POST /v1/goals/{id}/contract-approval | contract hash/version decision | R0; explicit authenticated execution consent, reuses approval service |
| GET /v1/goals/{id}/events?after=seq | event page / text-event-stream | R0 JSON replay; R1 SSE; seq decimal string |
| POST /v1/goals/{id}/cancel | expected_version + reason→202 request receipt | R0; terminal cancellation only after confirmed/reconciled effects |
| GET /v1/approvals | scoped pending/exact preview | R0; pagination and expiry |
| POST /v1/approvals/{id}/decision | effect_digest, expected_version, decision, Idempotency-Key | R0; one locked decision; duplicate same decision idempotent, conflict 409 |
| GET /v1/artifacts/{id} | protected metadata/content | R0; scoped hash check, no raw path parameter; no-store |
| POST /v1/ask | project_id/question/privacy/request_id→stream or AskResult | R1; local-only, explicit terminal event and provenance |
| POST /v1/memory | explicit approved fact/source/revision | R1; owner-only consented content, no model mass-assignment |
| GET /v1/memory/search | scoped query/limit | R1; validity/suppression before relevance |
| POST /v1/memory/{id}/suppress | explicit suppression receipt | R1; new retrieval/context exclusion; later purge status honest |
| GET /v1/runtime/status | model/hardware/profile/capacity/unknown | R1; no credential content |
| POST /v1/research | bounded ResearchRequest→202 goal/research ref | R2; configured provider/consent, no private browsing |
| GET /v1/research/{id}/evidence | claim/source/passages/status/uncertainty | R2; immutable source refs, safe content |
| POST /v1/goals/{id}/plan | bounded proposal or approved plan version | R3; model proposes, kernel validates and scopes |
| GET /v1/tasks and /v1/workers | typed task/fleet snapshots | R3; canonical DB/observed process states |
| GET /v1/usage | known/estimated/unknown values and caps | R3; unknown amount=null, separate cash/plan observations |
| GET /v1/audit | scoped safe action/exposure records | R3; authorized/accessible/observed distinguished |
| POST /v1/session/pair and /logout | one-use local code→session, csrf metadata | R1/R3 browser; rate limit, strict origin, cookie controls |

Add indexes/pagination, cap request/response bytes and reject invalid media type. Explicit request idempotency is scoped by actor/project/operation/key plus request hash; a repeated key with changed body is 409. Return same logical goal/effect after lost response. Response examples under fixtures/ define data shapes; reference IDs are synthetic.

## CLI journeys

R0: panestria goal submit --contract <fixture>; panestria goal status <id>; panestria goal events <id> --after <seq>; panestria contract approve <id> --digest <sha>; panestria artifact show <id>; panestria approve <request-id> --digest <effect-digest>; panestria deny/cancel. Commands resolve local identity from a protected file, never request arbitrary approved booleans. Domain denial/UNKNOWN returns nonzero or a documented pending exit, not false success.

R1: panestria ask --project <id>; memory add/search/suppress; hardware probe/report/benchmark; doctor. R2: panestria delegate --project <id> --question <text> with configured provider/limits; evidence verify. R3: build --contract <path> proposes validated DAG and shows queue/worker/check/approval states. All output includes safe correlation and evidence IDs.

## Four reference flows

**R0 synthetic Build:** submit validated contract→owner contract consent→atomic workflow enqueue→lease mock attempt→isolated edit→immutable evidence→independent checks→exact merge approval→PREPARED effect→synthetic CAS merge→confirmed receipt→task/goal completion. Restart at every boundary; WAITING_APPROVAL remembers whether to dispatch or finalize.

**Ask:** local identity/project/privacy→FTS recall with validity filters→bounded context pack→local model admission→stream with provenance→terminal status→separate consented correction. Network-off prompt cannot change route. If model missing, show degraded status and keep kernel/API usable.

**Delegate:** approved search disclosure→bounded subqueries/results→checked fetch broker→isolated reader snapshots→structured claims→citation/quote check→support/contradiction labels→brief/artifact/evidence. Reader never gains send/shell privileges; all error/truncation conditions survive output formatting.

**R3 two-worker Build:** approved bounded DAG→resource/known-cash reservations→two separate leases/workspaces→candidate outputs→fenced collection→integration/conflict detection→trusted suite on final tree→exact final approval→protected CAS effect→receipt→complete aggregate. Disjoint isolated passes are insufficient if the combined candidate fails.

## UI state and usability

Pages: intake tabs Ask/Delegate/Build, goals/tasks, task detail with evidence timeline, fleet, approval inbox, usage/exposure and trace links. Minimal accessible CSS/components, keyboard focus/contrast and plain statuses before elaborate graphs. A pending approve action is disabled until exact current preview/digest is loaded; UI cannot change payload after decision. On network failure keep pending state and fetch authoritative status. Source markdown strips active HTML; links never execute local files or scripts.

SSE handler uses idempotent normalized event reducer and decimal cursor; reconnect after last delivered event, bounded retry/backoff, snapshot refresh if cursor retention gap or unknown event schema. Session expiration clears sensitive views and stops reconnection. Unknown usage is visibly unavailable, not $0.0. Exposure fields show what was permitted, what the worker could access and what network metadata was actually observed; encrypted payload contents are not guessed.

## Revision 3 API/UI additions

Design typed authenticated profile read/correct/suppress, connection grant/revoke, quota observation/background policy/queue and read-only device/status routes under [the active specification](../specification/architecture/05-PERSONAL-PLATFORM-REVISION-3.md). Generate the concrete OpenAPI/schema from the implemented routes when coding; a plan entry is not an existing endpoint. Device read-only scope is server-enforced; profile/key operations never become generic artifact downloads. UI separates provider/owner/estimated/unknown quota and actual cash, exposes reserve/pause/preferred-provider policy, and retains source-bound progress/validation. The phone shows safe status/inbox and stale/offline state, with no sensitive offline cache or remote approval control.
