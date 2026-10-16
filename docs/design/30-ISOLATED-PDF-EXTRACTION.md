# Bounded static PDF text extraction

Explicit prerequisite: PR #79 (pinned minimal pypdf runtime), itself after #78.
Follow AOS-020's bounded reader contract; this adds a narrow PDF text-layer
extractor, not a rendered document, SourceStore or semantic/citation authority.

Only the fixed PDF program in the existing nonroot, read-only, network-none
Docker profile imports pypdf. Stage and verify the #79 source/license bundle
before/after runtime; mount only the fixed input/program/dependency bundle.
Use Python isolated/no-bytecode mode, strict PdfReader and public Configuration
with explicit decompression, page tree, stream/filter/work, recovery and XForm
limits. No external image decoder, OCR, fonts, binary, JS, file or URL access.
Controller never parses PDF objects or falls back to host parsing.

Narrow supported documents: at most 32 pages with nonempty digital text on every
page. Reject encryption, action/form/attachment/annotation constructs, external
streams and any image/Form XObject in the bounded reachable object graph. Reject
malformed/excessively nested/large graphs and decompression work. A missing text
layer or image page is UNSUPPORTED, not a successful empty or partial source.
Raw input stays capped at 2 MiB; decoded streams 2 MiB each/8 MiB total; text
512 KiB total. Page/text limits return TRUNCATED without partial complete text.
Runtime failure or ambiguous cleanup remains UNKNOWN. Known parse errors are
ERROR. Log only fixed reasons; never raw PDF-derived errors.

Join each NFC UTF8 page using a fixed newline/formfeed/newline separator and
return exact half-open UTF8 page spans. Validate a closed receipt, sizes, hashes,
version, normalization, spans and immutable bundle hash before exposing text.
Every PDF result has fixed text-layer/no-OCR/layout-unverified limitations.
Tables/columns/hidden text/reading order are not understood: a table fixture may
produce token text but must keep those limitations, never a structured table or
support judgment. Do not claim all PDF active features are detected; the object
filter is an additional restriction, and the actual sandbox remains mandatory.

Actual Docker fixtures cover text, multiple pages, compressed content, hostile
instructions as data, action/embedded/encrypted/image/empty documents, malformed
input, page/text/decompression bounds and deadline. Injected protocol mutation
checks are explicitly separate from OS evidence. No new image/model/provider
calls or credentials are needed. Component passes do not promote G1/G2/G3.

Reuse: pypdf 6.20.1/BSD-3-Clause immutable minimal bundle from #79; full installed
configuration and actual reader/filter/content-extraction paths inspected. Public
[extraction documentation](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)
explains whole-stream memory use and absent table/OCR semantics. No upstream
implementation copied. Pin and retain source hashes and actual Docker outcomes
with the qualifying source commit.
