# Immutable scoped source snapshot metadata

Start at freshly fetched main after the isolated HTML/text reader. This task
owns durable metadata and protected-byte lookup only; actual fetch/reader
composition and admission remain separate. No metadata service accepts model
text as a successful fetch, and no metadata-only test is provenance proof.

Add migration 0024: immutable research_source_snapshot, scoped to the exact
request/owner/project/goal/task, canonical body hash, artifact IDs with full
immutable hash/size/class foreign keys, extractor/completeness, and fixed
runtime/fetch receipt references. Use the existing global task_event sequence;
record and event commit in the caller's same PostgreSQL transaction. Refuse
unscoped/autocommit writes and destructive downgrade with history. Identical
retries return the original record; changed retry conflicts. Concurrent retry
must arbitrate all unique constraints, preserving #70's race fix.

Only trusted controller code persists a validated source record. Closed data
validation and artifact metadata do not establish actual fetched provenance.
Do not expose raw record creation as an agent/API tool. SourceStore will mint
source IDs from an admitted fetch and retain protected raw/text/receipt bytes
before metadata references are committed. Orphan bytes after rollback are
inert; a retry must verify them rather than overwrite/re-fetch silently.

Reads require actor plus exact request/task/source scope, revalidate the closed
body and canonical hash and full pinned artifact metadata, and use the scoped
ResearchBlobStore for actual hash/size-checked bytes. Keep failures explicit;
corrupt/missing/raw/truncated/unconfirmed data cannot produce usable passages.
The pure passage checker remains BYTE_MATCH_ONLY; actual provenance authority
will be required by the later SourceStore resolver. No task completion or
semantic support follows from this table.

Actual disposable PostgreSQL tests cover scope/pin forgery, concurrent retry,
immutability, shared rollback, global event ordering, direct constraints,
downgrade preservation and pg_dump/restore. Actual private filesystem lookup
checks retained bytes/corruption. No owner database, provider or credential is
needed. Claim/adjudication tables follow once source resolution is complete.
