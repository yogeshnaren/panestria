# Canonical research text and passage byte checks

Prerequisite: PR #66's closed research contracts. This independently reviewable
part of AOS-013 implements text/plain normalization and exact passage-byte checks
while the retained-source PostgreSQL/fetch/reader work remains pending.

Pin `nfc-utf8-v1` to strict UTF-8 decoding and Unicode 15.0.0 NFC. Preserve
whitespace, line endings, BOM and case. Verify the supplied raw content hash before
decoding; enforce declared and absolute byte caps before/after normalization.
HTML/PDF extraction is unsupported here, never approximated as plain text.

The byte checker revalidates contracts, requires a complete snapshot, exact
request/snapshot/normalization/text-hash bindings, whole-text hash/length, and
half-open offsets at UTF-8 character boundaries. Refuse noncanonical text or empty
passages. Return masked text with inherited maximum sensitivity and an explicit
BYTE_MATCH_ONLY verdict. Do not interpret source instructions or judge support.

These pure checks accept supplied bytes. They cannot prove that a snapshot or
artifact exists in protected storage, that a URL was fetched, that a broker was
authorized, or that a claim is true. A future SourceStore lookup must establish
those facts before exposing a citation; no model/public commit endpoint, usable
citation status, cloud call, database schema or release promotion is introduced.
This ordering brings deterministic normalization forward from AOS-013-S2 without
claiming the pending full S1/S2 cases. Test corrupted bytes, multibyte offsets,
scope/hash substitution, truncation, sensitivity and unsupported extraction.
