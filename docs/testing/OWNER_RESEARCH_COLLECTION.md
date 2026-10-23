# Collect sources for a staged PUBLIC question

This command runs a bounded collection and exports retained source excerpts and
diagnostics. It leaves the task VERIFYING with NOT_ASSESSED factual support.
It does not synthesize an answer or complete a goal. The website remains its
separate fixed demo. See [the lifecycle design](../design/55-OWNER-RESEARCH-COLLECTION.md).

## Required setup

Use a current private checkout with frozen dependencies, Docker/the existing
pinned reader image and a database at the current schema. Supply its existing URL
through `PANESTRIA_DATABASE_URL`, not a config/provider key. Do not use the owner
review DB for tests.

Live collection also needs an **actual qualified** joint research runtime and a
separately reviewed PUBLIC-web project policy. A Build-only/search-only/fetch-only
certificate, copied test fixture, configuration file or flag cannot supply this.
Search setup remains owner-deferred; this task does not install a service, select
upstream engines or issue a live certificate. The deterministic check below is
available independently of those live prerequisites.

Create a private `research.json` (mode0600) with this shape, using actual values:

```json
{
  "schema_version": 1,
  "owner_id": "OWNER_UUID",
  "project_id": "DEDICATED_RESEARCH_PROJECT_UUID",
  "root": "/absolute/private-research-cas",
  "certificates": "/absolute/separate-private-research-certificates",
  "certificate_sha256": "QUALIFIED_JOINT_CERTIFICATE_SHA256",
  "search": {"provider": "searxng-local", "origin": "http://127.0.0.1:CONFIGURED_PORT"},
  "fetch_connection": {"grant_id": "EXACT_REVIEWED_GRANT_UUID", "version": 1}
}
```

Both directories must already be canonical, owner-only (mode0700), and neither
may contain the other. The search settings must match the actual qualification.
[Prepare and confirm the dedicated project grant](OWNER_RESEARCH_POLICY.md)
before staging a contract pinned to it. Do not widen your existing offline Ask
project. A changed policy does not upgrade an old goal.

[Stage the PUBLIC question](OWNER_RESEARCH_SUBMISSION.md) with that exact current
policy and a compatible canonical contract: PUBLIC class, cloud_egress allow,
public-search and public-fetch capabilities, max_api_usd `"0"`, bounded attempts
and wall time. Other actor capabilities are refused by collection. Keep the
stored required checks; unadmitted citation/rubric runners remain refused.

[Prepare and separately review the public fetch declaration](PUBLIC_FETCH_CONNECTION.md),
then explicitly pin its exact grant UUID/version in these private settings.
Old settings without this binding cannot collect; declaration metadata alone
does not certify the runtime. Origins and cumulative application capacity apply
to all tasks sharing that version; revocation fences further hops/publication.

Create a private `queries.json` containing 1–16 selected PUBLIC query strings,
each at most512 UTF-8 bytes, without control characters or `!` engine selectors.
For example `["Selected public question about the chosen topic"]`. These exact
queries are the intended disclosures; the staged question is not exported whole.

```bash
umask 077
uv run --frozen panestria research collect REQUEST_UUID \
  --config /absolute/private-review/research.json \
  --queries /absolute/private-review/queries.json \
  --output /absolute/private-review/new-source-excerpts.html --public-web
```

The output parent must be private and the file new. Common output mistakes are
refused before dispatch; the final writer still refuses replacement/symlinks.
For JSON add `--format json` and choose a new private filename.

Expect `COLLECTION_STOPPED_AWAITING_SYNTHESIS_AND_SUPPORT`, a stop reason, IDs,
excerpt count and export hash. Inspect the private output: retained snapshot IDs,
exact passage offsets, byte/quote checks, source limitations and dispatch/error
observations. Source text stays untrusted. VERIFIED task completion or factual
support is never inferred from these byte checks. Source/body exhaustion can
stop queries early; failed transfers consume their reservations.

On an error, **inspect canonical state** with `research inspect`; work may already
be committed. The same command will not automatically resume or refetch a task
that has started. Missing/UNKNOWN acknowledgements stay RECONCILING, not a claimed
known completion. A normal stop stays VERIFYING; cancellation stays CANCELLED.
Current UI/history distinguishes status and expiry, not proof of a background
process. Use the existing scoped cancellation workflow for interruption; do not
delete retained history or reset a review database.

## Independent component check

```bash
umask 077
UV_CACHE_DIR="$HOME/.cache/uv" UV_OFFLINE=1 .venv/bin/pytest \
  tests/integration/test_owner_research_collection.py -q
```

The test drives owner stage→collect→private export, actual Postgres/CAS/local HTTP
and isolated reader, with **synthetic HTTPS and certificate fixtures only**.
It covers source/body exhaustion, one-request search unavailability, intent/query/
policy/config/bytes denial before activation, actual committed reservation plus
lost acknowledgement, concurrent goal locking, late cancellation and expired
lease fencing. It makes no live provider/model call and does not qualify G2.
