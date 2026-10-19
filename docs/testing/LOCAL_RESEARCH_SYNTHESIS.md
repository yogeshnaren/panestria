# Produce a local research draft

Use current main after the synthesis task PR merges. Panestria can turn already
retained PUBLIC research passages into a private answer draft. This command does
not search the web or verify that its generated claims are true. The separate
[collection guide](OWNER_RESEARCH_COLLECTION.md) explains obtaining retained
passages; actual search setup remains a prerequisite for a real public journey.

You need a migrated PostgreSQL database and the same owner/project and private
research CAS used for collection. The request must be VERIFYING with an ACTIVE
goal, valid retained passage evidence and a currently permitted local read.
You also need the existing pinned local model cache. No download or API key is
performed. Leave any owner model controller running; the command will refuse to
displace it, so use an idle authorized local slot for this check.

Create an owner-only `0700` directory for settings/exports. Save this as a `0600`
JSON file there, replacing UUIDs and paths with actual existing values:

```json
{
  "schema_version": 1,
  "owner_id": "<existing owner UUID>",
  "project_id": "<existing research project UUID>",
  "root": "/absolute/private/research-cas",
  "model_cache": "/absolute/existing/models",
  "runtime_directory": "/absolute/private/synthesis-runtime"
}
```

Paths must be canonical, absolute, disjoint, without symlinks. The CAS must exist
and be owner-only. The model cache contains only `blobs` and `manifests`. The runtime
is a separate private directory; the command creates it if absent. Do not put
settings, exports, credentials or model bytes in Git. Supply your database URL
through the existing private environment; do not paste it into terminal history.

From your Panestria checkout with frozen dependencies installed:

```bash
uv run --frozen panestria research synthesize <request-UUID> \
  --config /absolute/private/synthesis.json \
  --key first-local-draft --retain-local-draft \
  --output /absolute/private/draft.html
```

Expect `DRAFT_EXPORTED` with a hash and claim count, and a private HTML file with
generated claims, citation IDs, exact retained excerpts, shortening/omission flags
and limitations. `--format json` produces machine-readable provenance instead.
Only four bounded passage prefixes and the bounded question excerpt reach the
model; this is not comprehensive multi-source research. Support remains
NOT_ASSESSED and the task remains VERIFYING. Review the actual text and citations.

To recheck/export without running the model:

```bash
uv run --frozen panestria research inspect-draft <request-UUID> \
  --config /absolute/private/synthesis.json \
  --output /absolute/private/draft-review.html
```

Every output path must be new, with an existing owner-only `0700` parent. No file
is overwritten. Reusing the synthesis key never reruns a started inference. A
STARTED/UNCONFIRMED or FAILED receipt needs inspection, not a new key/retry loop.
If the CLI reports unavailable after an ambiguous operation, use inspect-draft
with a new output file. A cancellation, changed policy/task version, missing or
corrupt source/artifact blocks publication/reinspection. A failed export does
not undo an already retained draft. A successful export grants neither factual
support, task completion nor training-purpose rights.
