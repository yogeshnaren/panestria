# Reviewing quota observations

The scoped goal API now accepts owner quota reports and provides current/historical
reads. This supports the input “40% remains, resets tomorrow” with an explicit
reset timestamp and timezone. It does not start background tasks or enable a
provider. The preferred-provider queue, foreground reserve, verified billing
eligibility and offline result capture remain subsequent AOS-012 work.

Use an isolated current-main test checkout with the frozen environment and cached
pinned PostgreSQL image. Do not run another R1 database suite concurrently: the
fixture owns port 55439. It does not use the owner's 55432/55438 databases.

```sh
uv run --frozen pytest tests/unit/test_quota_contracts.py tests/integration/test_quota_ledger.py tests/integration/test_quota_api.py tests/integration/test_quota_migration.py -q
```

The tests submit synthetic metadata, validate real PostgreSQL/session scope, race
duplicate reports, wait for actual expiry, reject forged provider reports and
exercise immutable backup/restore. No provider/model/SDK requests are made.

For an already configured **schema head 29** loopback goal API, send the following JSON
to `POST /v2/quota/observations` using its existing bearer token, or its paired
browser cookie plus the existing CSRF header. Supply real scoped task/account
references and timestamps; the values below are illustrative, not live quota.
The account UUID is an opaque local metadata reference, not an account enrollment
or credential. The owner/project comes from the authenticated server configuration.

```json
{
  "schema_version": 1,
  "task_id": "00000000-0000-4000-8000-000000000001",
  "observation": {
    "schema_version": 1,
    "observation_id": "00000000-0000-4000-8000-000000000002",
    "scope": {
      "provider": "claude-subscription",
      "account_ref": "00000000-0000-4000-8000-000000000003",
      "model_ref": null,
      "window_ref": "session"
    },
    "source": "OWNER_REPORTED",
    "remaining": "40",
    "unit": "percent",
    "observed_at": "2026-10-16T08:00:00-07:00",
    "resets_at": "2026-10-17T08:00:00-07:00",
    "fresh_for_seconds": 900,
    "source_sha256": null
  }
}
```

Expect 201 for a new record, 200 for an exact replay and 409 for changed content
under the same observation ID/task. A future observation time is rejected. Use a
new ID for a new report. `remaining` is a decimal **string**, not a floating-point
JSON number; percentages never become requests/tokens or cash. Unknown is null,
including a later owner report with `remaining: null`; zero is a reported balance.
Do not submit credentials, email addresses, freeform notes or private response text.

`GET /v2/quota/observations/{observation_id}` returns the immutable report plus
server-derived freshness/confidence/effective balance. `POST /v2/quota/current`
accepts `{"schema_version":1,"scope":{...}}` using the exact scope above and returns
one latest report per source lane. Account, provider, optional model and window
are distinct: query session/weekly/model limits separately. Late-arriving older
reports do not replace newer observation times. Conflicting source lanes remain
visible; there is no synthesized usable-capacity total or source-priority rule.

Once freshness expires or reset passes, `effective_remaining` is null and confidence
is `UNKNOWN`; the historical report stays visible. Reset does not invent a new full
allowance. Exact replay does not renew freshness. Reports are capped at 24 hours of
freshness and 10,000 immutable records per project. Exhausting the storage cap
requires reviewed retention/archive work; it cannot silently discard audit data.

All responses say `OBSERVATION_ONLY`, use no-store, and create no invocation, budget
reservation or entitlement. The HTTP boundary accepts OWNER_REPORTED/UNKNOWN only.
Provider/estimate ingestion exists as a trusted metadata interface for future
collectors, but its synthetic tests do not establish actual supported-provider
telemetry. A source SHA is provenance, not a certificate. Missing/stale quota need
not block future authorized bounded best-effort work; no queue is enabled here.
