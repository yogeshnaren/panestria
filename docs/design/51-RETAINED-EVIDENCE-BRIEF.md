# Offline retained-evidence brief

This AOS-023-S2 component connects existing retained requests, sources and claim
checks to local owner inspection. It adds no external execution, semantic
support, research planner, HTTP API or second task/result database.

`RetainedBrief.inspect` takes an administrative local DSN, private CAS root,
actor and exact request/task IDs. It reads a repeatable-read, read-only Postgres
snapshot; validates request scope/hash, question artifact metadata and actual
protected question bytes; and reads claims in canonical sequence order. Existing
`ClaimStore.verify` recomputes deterministic evidence against retained source
proofs, bytes and quotes. Every displayed citation resolves again through
`SourceStore.resolve`, with retained URL, snapshot ID, UTF-8 offsets, hashes,
extraction limits and whether an original quote was supplied.

An unrelated assertion with a matching passage remains NOT_ASSESSED. Fabricated
quotes/missing sources are INVALID_EVIDENCE. Missing/corrupt claim payload/report
is UNAVAILABLE without unchecked text or URLs. Historical/current report hashes
stay separate. Failed lineage escalates classification. Semantic support and
contradictions are always NOT_ASSESSED. An export cannot complete a task.

Inspection does not search, refetch, extract or infer. It can read historical
cancelled/completed tasks without restoring execution authority. No DB writes,
new events or historical report changes occur. Its scoped event cursor uses the
existing global sequence. CAS reads retain the existing private-directory checks.

Bounds: 64 claims, 16 passages per claim, 65,536 question bytes, 8,192 displayed
passage bytes, 4 MiB aggregate output and DB query timeouts. Oversized individual
citation display becomes explicitly unavailable; aggregate overflow refuses
export. Nothing is silently truncated. Concurrent filesystem damage can make
inspection unavailable. This is a point-in-time snapshot, not ongoing monitoring.
Protected local CAS plaintext is not encryption.

The CLI requires the local owner's existing administrative DB access. IDs select
scope; they are not authentication tokens. Workers, phone clients and HTTP cannot
invoke this command through a public route. Exports require a new filename in an
existing canonical owner-owned mode0700 directory. Exclusive creation with a
directory descriptor, mode0600 and fsync refuses existing files/final symlinks.
Terminal output contains only closed metadata. Export copies are sensitive at the
derived classification and have their own owner-managed retention.

JSON unwraps protected text only into the private export. HTML escapes all
untrusted strings; has no scripts, styles, remote resources or active external
links; and declares a restrictive CSP. Source URLs are display-only text.
Embedded instructions remain data. Any loss of current evidence is explicit.

Still pending: admitted URL/fetch reservations, new-request orchestration,
qualified semantic judgments, objective synthesis, actual search configuration
and public-web runtime qualification, and full G2 acceptance. Original
citation/rubric acceptance runners remain unadmitted. No release gate is promoted;
paid SDK TC04 remains deferred, not passed.
