# Owner-only connection declaration review API

This is the HTTP review surface for the existing ConnectionReviewService. It
lets the configured owner inspect and decide an exact scoped declaration; it
does **not** connect an application, resolve roots, load credentials, certify a
connector or dispatch a task. It is a component of MVP-X09/AOS-008-S4–S5, not
completed onboarding or full TC05–TC08. UI and runtime GrantBroker remain pending.

The router is mounted with GoalApi, alongside existing scoped goal/quota routes.
Health-only applications leave it unmounted. No local service is restarted and
no new listener or configuration/credential source is introduced by this change.
Existing owner bearer authentication or paired browser sessions, exact host and
origin, mutation CSRF, body/security limits and database transaction reauthorization
apply. GETs also reauthenticate inside the database operation, so a session
revoked after the initial check cannot expose a manifest. No actor/project or
runtime permission is accepted from a caller-provided authority flag.

| Method / path | Input / result |
| --- | --- |
| POST `/v2/connections/reviews` | Explicit integer schema_version1, scoped task_id and closed ConnectionReviewRequest in `change`; returns201 new /200 exact retry |
| GET `/v2/connections/reviews/{proposal_id}` | Exact manifest, expected grant version, operation, effect_digest, policy reference and actual review deadline/state |
| POST `/v2/connections/reviews/{proposal_id}/decision` | Explicit integer schema_version1, exact effect_digest and `approve` or `deny`; historical receipt retries never renew a declaration |
| GET `/v2/connections/grants/{grant_id}` | Actual current revision/state, exact manifest and CURRENT/STALE policy |

Decision expected_version is already bound by the immutable review and digest;
it is not a separate mutable decision field. Every successful view/receipt says
`authority: DECLARATION_ONLY`, `conformance_status: UNVERIFIED` and
`runtime_available: false`, including when the manifest supplies a conformance
hash. Active means DECLARED_ACTIVE; it never means connected. Expiry and
revocation remain visible; replay of an old approval does not change them.

Request models reject additional fields, Boolean schema versions/counters,
unknown actions, raw root locators, credentials and caller approval flags.
Duplicate keys at any JSON object depth, nonfinite values, malformed/overdeep
JSON and oversize bodies refuse without echoing their content. Error responses
carry stable codes and no-store/no-referrer/nosniff headers. Unknown/foreign
resources never expose a manifest; conflict/stale/digest failures remain distinct
from syntax failures. Database unavailability returns a sanitized503.

Each service mutation and event commits in the existing caller-owned PostgreSQL
transaction. No scheduler kick or external action follows a decision. There is
no new state store, schema migration, task transition, root enrollment, native
client or provider/model/SDK call. Underlying exact owner/project/task/policy/
version/digest/expiry checks and event-lock-last ordering are retained.

Clean `86db5259a0fb1d4fc3aadbbd03cf1e129f416e5b` passes120 focused checks30.07s:
31 new real HTTP/PostgreSQL cases and89 existing declaration/contracts/quota/
session regressions. Actual session revocation before every transaction, owner/
project scope, policy staleness, review/grant expiry, revoke/replay, exact digests,
closed/ambiguous JSON, body cap, redaction and caller rollback are covered.
Task state/version/lease stay unchanged and no worker invocation is created.
Ruff, mypy200 source files and11 import contracts pass. Exact source/raw pins
are in [the component report](../../evidence/connection-review-api-2026-10-18/report.json).
This source was qualified before parking the candidate for the unrelated stdin
exit race; later main integration must preserve source pins and obtain fresh CI.

The original dirty29-case development run had28PASS/1FAIL: the oversized fixture
omitted Content-Type and correctly received415 before body-size checking. Only
the fixture header was corrected; JSON-only media and413 body caps are both
retained. Its original XML and the subsequent30-case development run remain
separate; the later caller-rollback case is included in clean120 qualification.

Reproduce this component without any provider credentials:

```bash
uv run --frozen pytest tests/integration/test_connection_api.py tests/integration/test_connection_reviews.py tests/unit/test_connection_contracts.py tests/integration/test_quota_api.py tests/integration/test_aos_009.py --junitxml=/tmp/connection-review-api.xml
```

Use disposable test stacks; do not point these tests at an owner database. This
does not run a GUI trial or vendor inference. No root locator/account is enrolled
and no existing owner checkout, service or profile is modified. Full account/
capability/source-purpose/current policy/lease/budget/approval/effect lifecycle,
secret boundary, broker enforcement and onboarding UI remain required. Neither
these metadata routes nor passing component tests promote G1/G2/G3 or start the
14-day owner trial.

Integrated main e9487aa includes the independently verified transport fix and
planning records. Normal merge c61dd0d preserves the original API source pins;
its clean integrated qualification passes the same120 checks32.82s. The separate
[integration record](../../evidence/connection-review-api-2026-10-18/integration-report.json)
retains its own raw XML and command corrections. Original86db525 artifacts are
unchanged. Full exact-head CI remains a separate publication/merge prerequisite.

Full CI39106917587 at a1342c0 found the checked-in OpenAPI snapshot missing the
four new mounted routes:1864PASS/1FAIL/51 live excluded/one warning524.08s. The
unchanged parity assertion was retained. Regeneration changes only those four
paths; every older path/component is identical. Dirty correction32 passes15.87s;
clean21bfa80 parity1 passes0.63s. The separate
[correction record](../../evidence/connection-review-api-2026-10-18/openapi-correction-report.json)
preserves both source states and the original failed full-log hash. Fresh full
exact-head CI is required; no runtime or acceptance authority changes.
