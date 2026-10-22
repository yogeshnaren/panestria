# Explicit PUBLIC Build plan input

A separate `mission-control serve --build-intake` mode stages existing PUBLIC,
zero-API-cash contract/proposal/inventory JSON through `PlanSubmissionService`.
It uses the configured activity owner/project and a distinct origin-bound session
purpose/cookie. Refuse combinations with Ask, research intake, evidence/review
stores. Default metadata and other modes mount no plan submission routes.

The browser imports or pastes one bundle containing `contract_document`,
`proposal`, `inventory`, reviews the entire input and explicitly confirms PUBLIC
intent. Keep the existing 65536-byte total HTTP body cap. Do not invent a planner,
worker inventory or qualification certificate. The canonical parsers and
PlanValidator enforce contract/inventory hashes, DAG, paths, capabilities, checks,
budgets and scope. Preserve IDs and declared worker identities unchanged.

POST `/v1/mission/build/plans` requires exact boolean `public_plan: true`. Reuse
canonical staging with an idempotency key derived from the immutable plan UUID.
Under the project lock, reauthenticate session/CSRF on the committing connection
before staging and again before commit. The existing service atomically stages
the goal, original checks, proposal, validation and pending fifteen-minute plan
consent. No accepted tasks, attempts, leases, permission grants or worker/model
execution. Plan acceptance is a separate existing CLI workflow; it is not merge
approval or runtime qualification.

GET `/v1/mission/build/plans/{plan_id}` reuses PlanStore's owner/project/hash/current
policy validation and returns the full PUBLIC contract and retained plan with
actual goal/plan state, consent digest/expiry and execution authority NONE. Read
inspection rolls back; final authentication after protected I/O hides revoked
replies. An expired pending consent is inspectable but cannot be accepted by the
existing canonical service. No copied database state, new table or migration.

The UI renders JSON as inert text and keeps input/receipts only in memory.
Ambiguous POST replies block new submission; recover by GET of the same plan UUID,
including after reload, with no automatic POST retry. Input and receipt clear on
page hide/access loss. A recovered ACCEPTED state describes a separate canonical
owner action; intake itself supplies no acceptance, scheduling or effect dispatch.

Connected tests use actual PostgreSQL, Git, loopback HTTP, CLI pairing and Chromium
with declared fixture inventory and explicit lost-ack injection. Those observations
are not native/provider qualification, original AOS-028 scenario completion, G3 or
MVP acceptance. Full inbox/dispatch, qualified Delegate, phone and remaining
revision-3 obligations remain open.
