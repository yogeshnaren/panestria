# Generate and retain local research queries

Panestria can now turn an **already staged PUBLIC question** into a small local
search-query proposal. It retains the exact bounded input/output, model identity,
hashes, token counts and request latency. It makes no web request, grants no web
permission and does not mark the question answered or verified.

Start with [question staging](OWNER_RESEARCH_SUBMISSION.md). Use a separate private
CPU configuration in the same format as [local synthesis](LOCAL_RESEARCH_SYNTHESIS.md):

```json
{
  "schema_version": 1,
  "owner_id": "EXISTING_OWNER_UUID",
  "project_id": "EXISTING_RESEARCH_PROJECT_UUID",
  "root": "/absolute/private/research-retained",
  "model_cache": "/absolute/existing/dedicated/models",
  "runtime_directory": "/absolute/private/query-runtime"
}
```

The file is mode0600, its retained root mode0700. Root, cache and runtime paths
must be absolute, canonical and non-overlapping. The existing dedicated cache
must contain the pinned model; this command downloads nothing and never falls
back to an API. CPU capacity and exact owned-runtime startup remain checked.
The database environment is the same canonical database used to stage the request.

```bash
panestria research plan-queries REQUEST_UUID \
  --config /absolute/private/query-plan.json \
  --output /absolute/private/queries.json \
  --key first-local-query-plan --retain-local-plan
```

Expect `QUERY_PLAN_RETAINED`, one to three queries and metadata on stdout.
`queries.json` is private create-once JSON suitable for the collector's
`--queries` argument. Read/review it before the separately authorized collection:

```bash
panestria research collect REQUEST_UUID \
  --config /absolute/private/research.json \
  --queries /absolute/private/queries.json \
  --output /absolute/private/collected.html --public-web
```

Collection still requires its own explicitly configured search backend, PUBLIC
policy and current joint runtime qualification. Search setup remains owner-
deferred. Query generation never chooses engines or creates those permissions.
Continue with [retained evidence review](RETAINED_EVIDENCE_BRIEF.md) and
[local answer drafts](LOCAL_RESEARCH_SYNTHESIS.md). Queries and cited drafts are
untrusted proposals; qualified factual support remains a separate unfinished gate.

To export an existing plan again without model startup or even the cache:

```bash
panestria research query-plan REQUEST_UUID \
  --config /absolute/private/query-plan.json \
  --output /absolute/private/queries-again.json
```

This validates the original scoped input/output artifacts and shows known
`model_ref`, `model_digest`, `input_tokens`, `output_tokens` and
`model_request_elapsed_seconds`. Latency measures the model request, excluding
startup/setup; `query_quality` stays NOT_ASSESSED. These measurements live in the
protected retained output referenced by canonical events, not an unsaved console
counter. Raw questions/queries are kept out of event payloads and normal receipts.

The planner receives only the first512 UTF-8 bytes of the question; shortening is
visible and the full original question hash is retained. It has no tools, outputs
up to three distinct queries of at most256 bytes each, uses a fixed local model,
at most512 output tokens and a60s request deadline. It does not rewrite the staged
contract, acquire a task attempt, widen source limits or create acceptance verdicts.

One acknowledged intent is permitted per request. Replaying the same key returns
the original receipt without another call; a different key cannot replace it.
Concurrent callers see the first intent as UNCONFIRMED. A crash, malformed output,
unavailable model or cancellation retains the intent/failure, with no blind retry.
Fix export-only errors by choosing a new private output path and reading the
retained plan. Failed generation needs explicit investigation/new bounded work,
not a retry loop. Input/policy/version/epoch changes before disclosure/publication
fence output. Retained historical inspection grants no execution or training right.

[Evidence](../../evidence/research-query-plan-2026-10-21/report.json) includes
actual PostgreSQL/private CAS/CLI checks with synthetic model outputs and a
separate actual cached CPU run at its original source: two queries,143 input and
23 output tokens,4.94s model-request latency. That single synthetic-question smoke
does not establish query quality, live search readiness, G2 or G3.
