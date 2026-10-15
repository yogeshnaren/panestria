# Bounded public HTTPS fetch transport

Start from freshly fetched main; independent of #76 native conformance. This is
an internal trusted-controller transport for already authorized PUBLIC URLs,
not an API, policy grant, reader, source ID mint or usable citation authority.
Keep the provider CONNECT allowlist unchanged. Reuse its public-unicast/exact-peer
predicates, including mapped/tunnel/site-local/documentation/scope denials.

Support HTTPS on port 443 only in this transport. Reject credentials, fragments,
control characters, unsafe DNS names, private/nonpublic/mixed DNS answers and
unsupported schemes/ports before connecting. Bound DNS workers and connection
admission; pin one validated numeric address and verify the actual peer before
and after TLS, with ordinary certificate/hostname validation and no environment
proxy. Never let the HTTP library re-resolve the hostname.

GET uses fixed secret-free headers only, no cookies/auth/user headers, no
compression, no connection reuse or implicit retry. Validate every redirect,
including relative locations, with fresh DNS and the same checks; bound the
redirect count, header/framing bytes, body bytes, overall time and cancellation.
A deadline-aware raw TLS reader must check on every receive so slow status/header,
chunk framing or body trickles cannot reset a per-read timeout indefinitely.

Retain only capped bytes and explicit COMPLETE/TRUNCATED/ERROR/UNSUPPORTED
outcomes with bounded redacted hop metadata and hashes. URLs and bodies stay out
of repr/errors. A retained body hash does not prove extraction, source ownership,
claim support or policy authorization. Later orchestration must persist scoped
artifacts/receipts and establish that authority before SourceStore exposes text.

Use actual public TLS fetching where permitted and independent protocol/SSRF
fixtures with injected DNS/socket seams. A private local fixture must never be
presented as proof that production private addresses are allowed or that a public
web fetch passed. Keep all failures and actual source/environment limits visible.
