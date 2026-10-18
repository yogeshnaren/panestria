# Admitted fetch/read/retain controller

The trusted `AdmittedFetch` controller binds current PUBLIC research authority to
the existing fetcher, isolated reader and protected source store. A successful
call returns a retained snapshot ID; the owner can inspect subsequent retained
claims through [the offline brief CLI](RETAINED_EVIDENCE_BRIEF.md). The component
does not expose arbitrary fetch callbacks to workers or add a new Delegate route.

The workflow constructs `FetchPlan` from the exact stored research request,
validated goal contract, current reviewed policy and runtime configuration. It
must have a current attempt/epoch, explicit `public-fetch` capability, PUBLIC
goal/question, cloud allowance, zero SDK budget, current public-web policy and
an actual separately qualified `PublicFetchCertificateStore`. Runtime hashes
alone and a search/Claude certificate do not grant fetch access.

Each source reserves count and cap+1 body capacity before transport, with no
automatic refund/retry. Each redirect commits disclosure before DNS. Failure is
FETCH_ERROR or READER_ERROR; missing receipts are UNKNOWN. RETAINED binds an
actual captured source. The rows are historical observations, not support or
goal-completion authority. Use the [design](../design/52-ADMITTED-FETCH-READ-RETENTION.md)
for byte accounting, cancellation/crash limits and restore rules.

Reproduce only local component checks with Docker and frozen dependencies:

```bash
uv run --frozen pytest tests/integration/test_fetch_admission.py \
  tests/integration/test_search_admission.py \
  tests/unit/test_research_public_fetch.py \
  tests/integration/test_research_brief.py -q
```

These use real disposable Postgres/CAS, actual isolated Docker reader and the
inspection CLI. HTTPS/DNS/TLS responses and runtime certificates in this suite
are explicitly synthetic; no public site, paid API or model is called. They
verify durable admission before the synthetic transport, actual source retention
through a claim to an owner brief, concurrent source/byte limits, lost acknowledged
commit, failed transfer consumption, redirect denial, cancellation after retention,
certificate purpose, actual dump/restore/global events and downgrade refusal.
Existing wire fixtures separately check callback order before DNS.

This is not live OS/SSRF/reader qualification or full G2. Actual setup/qualification
must precede live calls. The owner chose to configure search later; no service,
engine, credential or issuer is installed by these checks. No original gate or
semantic obligation is waived. Do not manufacture an operator certificate from
fixture reports or retry an UNKNOWN URL to replenish the budget.
