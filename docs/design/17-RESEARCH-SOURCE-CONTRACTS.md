# R2 research source contracts: first implementation slice

Selected slice: AOS-013-S1, independent source work while R1 live prerequisites
remain pending. Current main has durable scoped tasks, immutable artifacts and
the sandbox interfaces. This task does not promote G1/G2, enable Delegate, make
web requests or add a research reader/tool permission.

Start with closed versioned transport contracts. This first PR narrows to the
contract boundary; immutable database metadata follows in the next task using
the next additive migration after 0022. Preserve historical prospective
revision `0005_research` in old design references; it is not an applied revision.
Keep owner/project/goal/task/request/snapshot/claim relations in composite foreign
keys. No worker/model supplies canonical snapshot IDs or fetch authorization.

Raw/text artifacts reuse protected artifact identities and task lineage. The
snapshot binds requested/terminal URLs, redirect receipts, observed timestamp,
HTTP status/content type, raw/text hash and byte limits, extractor/normalization
versions, completeness and maximum input/source classification. An unverified
URL or model-authored ID cannot become trusted fetch provenance. Storage/write
authority stays with the future broker/quarantined reader; no arbitrary upload
or model-facing commit endpoint is introduced here.
Redirect receipts are protected artifact references with the same task and
maximum classification, not worker-provided URL strings. Their actual body,
addresses/status/chain verification and retained-fetch authority remain broker/
reader obligations. Opaque binary content cannot self-assert complete extraction.

Passage references use half-open UTF-8 byte offsets and a pinned normalization
version. They bind an existing snapshot/text hash. Quote/support/conflict verdicts
are separate immutable observations with verifier identity and evidence refs;
neither a matching hash nor valid offsets establishes semantic support.

This first task's accepted outcome is contract and byte-budget integrity, not
source authority, a completed AOS-013, its schema case, or a research brief. Subsequent
slices implement canonical normalization/resolution, verified source commit and
claim attachment with the actual retained-successful-fetch prerequisite. Missing
raw/text, truncation, unsupported extraction and failed fetch never become usable
complete citations. Keep claim-support judgments pending until their verifier.

Test malformed authority fields, byte budgets, snapshot completeness and passage
reference bounds. The next schema task must also test real PostgreSQL
scope/immutability/data preservation and downgrade guards. Record source-bound results; leave full item
cases pending wherever their broker/reader/extraction assertions do not yet exist.
