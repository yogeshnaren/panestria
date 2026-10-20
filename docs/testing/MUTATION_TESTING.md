# Mutation testing and test value

The first pilot deliberately injects faults into five production functions:
policy authorization, public-address filtering, connected-peer pinning,
allowlisted DNS resolution and entailment scoring. It uses pinned mutmut 3.8.0,
two workers and a ten-minute ceiling, with no provider calls, model loading,
Docker, owner databases or services. Existing local Unix-socket denial behavior
is exercised. This is a bounded sample, not a repository-wide mutation score.

## Actual result (2026-10-19)

| Same 318 mutations | Detected by failing test calls | Survived | Unresolved | Raw detection fraction |
| --- | ---: | ---: | ---: | ---: |
| Original assertions | 252 | 66 | 0 | 79.25% |
| Focused regression improvements | 294 | 24 | 0 | 92.45% |

The clean final source is `ae9c4a2`; the original assertion run records its dirty
configuration and every input hash. The five production function files were
unchanged between observations. No survivor was excluded to improve the score.
Each completed campaign took about 32 seconds on this workstation; that is an
observation, not a runtime promise. Full reports, input hashes, actual failing
node IDs and the original survivor diffs are in
[evidence/mutation-pilot-2026-10-19](../../evidence/mutation-pilot-2026-10-19/).
Two initial tooling/environment failures (copy destination, restricted Unix
socket) remain explicitly recorded; neither contributes a successful score.

Faults newly detected include an incorrect quality-score denominator, missing
confusion-matrix labels, accepting the wrong prediction container, losing the
policy effect fingerprint or transport enforcement, allowing unapproved hosts
or ports to reach DNS, dropping TCP selection, accepting IPv6 scope 1, and
incorrectly denying permitted synthetic local work. A few focused assertions
and nine additional collected cases detect 42 previously surviving faults.
These are tests of Panestria's behavior, not tests that pytest can fail.

## Review of the remaining 24 survivors

22 change diagnostic strings or the distinction between canonical and legacy
denial explanations while retaining the denial itself. They remain visible
quality gaps, not automatically equivalent or waived. Exact error-message
coverage is lower priority than authority, privacy and transport enforcement.
Two are contextually equivalent under current closed inputs: changing
`rpartition` to `partition` for the fixed hostname allowlist; and changing the
prediction-identity guard from `or` to `and`, where fixed cardinality plus
subsequent guarded lookup still rejects missing, duplicated or foreign IDs.
This reasoning is restricted to the current inputs and code; raw counts retain
both. No `no mutate` pragmas or type-filter exclusions were introduced.

A mutation is counted as detected here only when the tool exits with test
failure **and** the observer records actual failing call-phase node IDs with no
setup/teardown errors. Internal runner failures, timeouts, crashes, missing
observations and no-test results remain UNRESOLVED. Clean/stats baselines must
pass. All failing call IDs are retained; this avoids confusing coverage with
actual detection or only reporting the first failure.

## Promoted fast regression subset

`make test-critical` runs 21 existing/new cases selected from actual detection
witnesses. Together their recorded failures cover all 294 detected pilot
mutations. Their ordinary clean run passed in 0.68s. The machine-readable
[critical manifest](mutation-critical.json) binds this recommendation to its
source report/hash; it is a greedy witness selection, not proof of a globally
minimal suite. The subset's own JUnit file is `evidence/ci-fast-critical.xml`.

Normal PR CI still runs every non-live test in the four existing lanes. No
broader behavior, database, sandbox, crash recovery or live release test was
removed merely because it did not detect a fault in these five functions.
A zero pilot contribution cannot establish that an unrelated test is redundant.
Use this subset for rapid feedback; it cannot establish a CI or release pass.
Future promotion/removal decisions need actual changed-area mutations, unique
requirements, overlapping fault witnesses and measured execution cost.

## Run and inspect

```bash
uv sync --frozen --group dev --group mutation
uv run --frozen --group mutation python tools/mutation_run.py \
  --output .panestria-metrics/mutation-$(date -u +%Y%m%dT%H%M%SZ)
make test-critical
```

Use a new output directory every time. Each campaign copies tracked source,
tests, config and tooling into its own workspace; it never mutates the checkout
or reuses cached results. The saved report binds source commit, dirty state,
input hashes, Python/tool versions, scope, status, duration and per-test fault
witnesses. Inputs must be committed for new files to participate. Copy reports
to durable storage before removing a disposable checkout. About 16 MiB was used
per pilot workspace; nothing is automatically deleted or pruned.

For a surviving ID from `report.json`, inspect the exact generated difference:

```bash
cd <campaign>/workspace
<repository>/.venv/bin/mutmut show '<mutant ID>'
```

The separate **mutation pilot** GitHub workflow is manual (`workflow_dispatch`)
and retains reports, observations and logs for seven days. It is deliberately
absent from routine PR CI. Its success means the experiment completed with
classified results; survivors remain review work and do not become a release
pass. Archive important runs locally because hosted artifacts expire.

Tool behavior/configuration was checked against the
[official mutmut documentation](https://mutmut.readthedocs.io/en/latest/).
