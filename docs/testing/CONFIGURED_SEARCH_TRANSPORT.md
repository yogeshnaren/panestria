# Configured local search transport

`LocalSearxngProvider` supplies the missing search transport for the next Delegate
controller. It contacts one explicitly configured literal loopback HTTP origin
and posts a bounded PUBLIC query to `/search`. Nothing discovers an instance,
installs a service, chooses a replacement provider or exposes this broker as an
owner API. It returns untrusted, unfetched URL/title/snippet candidates; these
are not source snapshots, facts, citations or task completion.

The protocol follows SearXNG's [official API](https://docs.searxng.org/dev/search_api.html):
POST form data with `q`, `format=json`, the general category and first page.
JSON must be enabled in the configured instance; HTTP 403 becomes the explicit
`search_json_disabled_or_denied` setup error. Query routing modifiers `!` and `!!`
are rejected because SearXNG [uses them to select engines or redirect externally](https://docs.searxng.org/user/search-syntax.html).
The request remains an off-device disclosure when a local frontend forwards it
upstream. Deployment must explicitly approve that service's upstream engines;
the client cannot prove their configuration or spending from its HTTP response.

The trusted caller must provide `before_send(disclosure)`. It must check current
owner/project/task permission, enforce the durable query count and commit the
query/configuration/scope hashes to the outbound disclosure ledger before
returning. No socket exists before that callback succeeds. The adapter never
grants policy or creates a second task store. Binding that callback to the kernel
is implemented in [durable search admission](SEARCH_ADMISSION.md). Exposing the
bounded Delegate workflow remains subsequent work; do not connect
an untrusted caller to a permissive callback.

V1 accepts PUBLIC plain queries up to 512 UTF-8 bytes, response budgets of
1 KiB–1 MiB (64 KiB default), at most 16 returned candidates (8 default) and an
absolute 0.1–30 second deadline (10 default). Existing Panestria HTTP framing
and absolute-deadline readers are reused. Deadline/cancellation covers trickled
headers and body reads. Only static literal loopback origins are accepted for
this separately configured operator service. This does not permit fetching
private URLs discovered in search results: those still go through the existing
public HTTPS broker's DNS/IP/redirect/TLS checks.

No ambient proxy, browser cookie or authorization header is read or forwarded.
The client follows no redirect and makes no automatic retry or fallback. Wrong
MIME, encoded responses, byte excess, malformed/duplicate JSON and a query-echo
mismatch fail explicitly. Syntax-invalid/duplicate/excess candidates are counted
as omitted; upstream engine errors remain counted. Text stays untrusted data,
including injected instructions. Cash and remaining quota remain unknown.

```bash
uv run --frozen pytest tests/integration/test_configured_search.py \
  tests/unit/test_research_public_fetch.py -q
```

Expect 76 passing checks on the recorded clean candidate. The HTTP server is a
disposable synthetic loopback fixture on an ephemeral port. It is not an installed
SearXNG instance or live upstream proof. The
[source-bound report](../../evidence/configured-search-transport-2026-10-18/report.json)
preserves that distinction and the inspected official protocol/source revision.
No upstream implementation was copied, installed or executed.

Live configured search qualification and the bounded brief flow
and qualified semantic support remain pending. Prior local/native entailment
preflights do not grant automatic support authority. All R2 items remain
IN_PROGRESS, and G2 remains NOT_RUN. Ask/Build are unchanged when search is absent.
