# Shared research runtime component check

See [the decision and limits](../design/53-SHARED-RESEARCH-RUNTIME.md). This
connects existing trusted controllers; it is not yet an owner-facing Delegate
submission command or live provider qualification.

From a private, clean checkout with frozen dependencies, Docker and the existing
pinned reader image available:

```bash
umask 077
UV_CACHE_DIR="$HOME/.cache/uv" UV_OFFLINE=1 .venv/bin/pytest \
  tests/integration/test_shared_research_runtime.py \
  tests/integration/test_search_admission.py \
  tests/integration/test_fetch_admission.py -q
```

Use the disposable test Postgres project/port. Do not run another R1 fixture
suite concurrently or use the owner's review database. No service installation,
model download, provider login, external search or inference is performed.

Expect a search over real loopback HTTP, acknowledged query/hop audit before I/O,
synthetic HTTPS bytes through the actual isolated reader, retained source and
quote verification, and an inspectable brief with `NOT_ASSESSED` semantics. The
same policy/certificate/request/contract/lease spans search and fetch. Missing
union case reports, wrong certificate purpose or substituted search settings
must deny before dispatch. Existing standalone search/fetch cases remain valid
for their original narrow profiles. The task stays `RUNNING`; these components
do not claim semantic support or complete a goal.

Live search setup remains deferred by the owner. Only an actual source- and
configuration-bound qualification may issue a live joint runtime certificate;
the deterministic fixture must never be copied into an operator store. Original
G1/G2 requirements and the deferred paid SDK check are unchanged.
