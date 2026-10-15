# Isolated bounded text and HTML reader

Independent from #77's HTTPS transport; start at freshly fetched main. Extract
untrusted supplied bytes with a fixed reviewed Python program inside the existing
nonroot, read-only, network-none Docker profile. The native inference/auth process
never parses fetched HTML. This component is not SourceStore, fetch authority,
claim support or a release/security certificate.

Support strict UTF-8 text/plain and text/html. Pin Unicode 15.0.0 NFC and exact
raw SHA/length; use Python's standard HTMLParser as a tokenizer, never execute
HTML/JavaScript, resolve external entities, fetch embedded resources or open
source-selected paths. Skip script/style/head/template/noscript content, comments,
forms and embedded objects. Preserve tokenizer text and explicit block boundaries;
record extractor and normalization versions. HTML offsets refer to normalized
text only. CSS visibility/layout is not interpreted: hidden CSS text can remain.
No browser-rendered visibility, raw-byte mapping or table interpretation is claimed.

Raw input is at most 2 MiB. Declared normalized text is at most 512 KiB for this
reader profile; output exceeding that cap is explicitly TRUNCATED and cannot be
used as a complete source. Controller requires the actual Docker receipt, fixed
program/input hashes, strict bounded JSON/base64 output and exact Unicode/text
hash/length before exposing text. Invalid UTF-8, PDF/other formats, missing or
changed input, output pressure, parser/runtime failure or unknown cleanup cannot
claim successful extraction. PDF extraction remains a separate required R2 task.

Only the one synthetic/scoped input and reviewed reader/trampoline programs are
mounted. No host home, credentials, database, native login or network gateway is
visible. Cancellation/deadline uses the existing exact-container supervisor.
Actual Docker tests cover hostile markup and instructions as data, resource
bounds and cancellation; they do not prove source provenance or semantic support.
