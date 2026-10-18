# One policy for search and fetch

Task outcome: use admitted search and fetch/read/retention with the **same**
immutable request, contract, reviewed project policy, task and attempt. This
depends on durable search (PR112), private brief inspection (PR113) and admitted
fetch (PR114). It does not submit a new owner question or qualify a release.

## Problem and decision

The project policy has one runtime certificate hash. Standalone search requires
`PUBLIC_SEARCH_RUNTIME_ONLY` / `public-search-v1`; standalone fetch requires
`PUBLIC_FETCH_READER_RUNTIME_ONLY` / `public-fetch-reader-v1`. Changing the policy
between components invalidates the contract's pinned policy. Treating either
component certificate as permission for the other would widen its authority.

Add the explicit pair `PUBLIC_RESEARCH_RUNTIME_ONLY` / `public-research-v1`.
**Both** certificate stores require the base OS boundary cases AOS-008-TC03 and
AOS-010-TC03 plus the union AOS-019-TC02, TC03, TC04 and AOS-020-TC01, with protected
content-addressed reports. Missing either component's report denies both stores.
The certificate must match the running runtime, actions, trust profile and expiry.
No live issuer or certificate is introduced by this task.

## Runtime and configuration identity

`execution/research_runtime.py` retains the standalone version dictionaries and
adds `research_runtime_versions(settings)`. The joint version pins all package
Python source, exact validated local search settings, the existing fixed fetch
and no-network reader configuration, Python/OpenSSL/kernel, reader image and
UID/GID. It includes the separate component configuration hashes and a canonical
aggregate hash of those hashes and the joint profile. Changing the endpoint,
response bounds, result count, deadline, source or reader runtime requires a
new matching qualification.

Search plans and search disclosure retain the **search settings hash**. Fetch
plans retain the **fixed fetch configuration hash**. The aggregate hash is the
certificate identity, never a replacement for either plan's configuration.
No schema migration or historical plan/hash rewrite is needed.

`AdmittedSearch` selects the explicit joint profile from the supplied certificate
store and independently recomputes its expected versions. `AdmittedFetch` requires
the exact search settings for that profile and validates a private copy. Omitted
or substituted settings fail before dispatch. Supplying search settings to the
standalone fetch profile also fails; there is no silently ignored configuration
or certificate fallback. Both controllers recompute current runtime identity and
retain their existing current policy/lease/deadline/cancellation fences.

## Connected check and limits

The deterministic integration uses actual disposable Postgres transactions,
reviewed policy revisions, loopback search HTTP, query/hop disclosure commits,
source/body reservations, CAS, the isolated Docker reader, quote checking and
private retained-brief inspection. HTTPS transfer and qualification certificates
are explicitly **synthetic test fixtures**. No installed SearXNG, upstream engine,
public HTTPS/TLS or live OS qualification is proved by these fixtures.

The same policy hash, request/contract, attempt and lease are asserted across
both audit ledgers; no policy switch or task completion occurs. A real quote
can be attached to an unverified interpretation: the resulting brief must remain
`NOT_ASSESSED`. Search snippets never become retained evidence or instructions.

Actual search setup is owner-deferred. Stable-runtime qualification, owner
new-question orchestration, semantic support and full G2 remain pending. Existing
standalone certificates retain their narrow purposes; historical evidence remains
bound to its original source. This task neither refreshes those certificates nor
repeats unchanged paid/native/model probes.
