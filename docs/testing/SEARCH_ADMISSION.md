# Durable search admission

This component connects `LocalSearxngProvider.before_send` to canonical Postgres
authority and a durable task-wide query/disclosure ledger. It is the next part
of AOS-019-S1. It does not yet expose a Delegate CLI/API or enable live search.

The trusted workflow constructs `SearchPlan` from the retained research request,
stored contract, current owner-reviewed policy and exact operator client settings.
It supplies a current attempt ID/epoch, `PublicSearchCertificateStore` and PUBLIC
`SearchQuery` to `AdmittedSearch`. It must compile queries only from explicitly
PUBLIC context and present the fixed query budget to the owner. Workers cannot
supply a permissive callback, certificate, policy grant or replacement plan.

`prepare()` commits an immutable per-task plan. `search()` rechecks authority,
consumes one ordinal and commits the hash-only disclosure before network I/O.
Repeat queries fail with `search_already_dispatched`; additional distinct queries
after the limit fail with `search_query_budget_exhausted`. New attempts and research
request IDs do not reset that budget or the wall clock. HTTP 403/429 remain explicit
setup/quota failures and consume a possible disclosure, with no fallback or refund.

Inspect `search_plan`, `search_dispatch` and `search_outcome` scoped through their
canonical task/goal owner. An absent outcome means UNKNOWN, including after a
crash. Never delete or edit it to retry. A returned response hash is a historical
local-service observation, not upstream usage, source retention or support proof.
No raw questions, URLs, snippets or model instructions appear in this ledger.

Reproduce the component checks with Docker and existing frozen dependencies:

```bash
uv run --frozen pytest tests/integration/test_search_admission.py \
  tests/integration/test_configured_search.py -q
```

The suite uses actual disposable Postgres databases and ephemeral loopback HTTP.
Certificates are explicitly **TEST_FIXTURE_NOT_LIVE**. It checks acknowledged
commit before HTTP, lost commit acknowledgements, rollback, concurrent budget
consumption, lease replacement, deadline/private-task/policy refusal, real goal
cancellation, setup/quota errors, immutable audit and actual backup/restore.
Migration checks preserve prior rows and compare the observed schema fingerprint.
It makes no external search, inference, paid API or owner-database call.

The [clean-source report](../../evidence/search-admission-2026-10-18/report.json)
records 40 passing checks: 19 for the new component, historical connection-audit
restore and the local API suite. Prior failures and their corrections are listed;
they are not counted as passing evidence.

Live search still requires a separately configured owner-approved SearXNG service,
its inspected upstream/no-extra-spend configuration and actual source-bound OS
qualification. `PublicSearchCertificateStore` rejects a native Build-only purpose;
no live search certificate is issued here. The prior Build certificate is also
historical after package source changes; qualify a selected stable checkout when
using that CLI. Do not repeatedly run native inference to validate search-only
changes. Original R1/G1, R2/G2 and SDK-deferred obligations remain unchanged.

Next: connect admitted search/fetch to the existing isolated reader, retained
sources/quotes/claims and an inspectable research brief. Qualify semantic support
separately; current failed preflights cannot produce automatic SUPPORTED claims.
