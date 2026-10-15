# Read-only MVP readiness inventory

Run from the selected candidate checkout:

```bash
uv run --frozen python -m panestria.verification.readiness --gate G1
uv run --frozen python -m panestria.verification.readiness --gate G3 --pretrial
uv run --frozen python -m panestria.verification.readiness --gate G3
```

Use `--root /absolute/checkout` to inspect another checkout. The tool reads the
active gate/catalog manifests and parses test source without importing or
executing inspected tests. It reports the inspected Git commit, dirty status,
case IDs, literal registrations, expected-node mapping gaps and explicit live
annotations. G3 uses the complete revision-3 manifest: 156 pretrial cases and
157 final cases. The final owner/trial case is never silently omitted.

Exit codes: 0 means the selected static mappings are registered; 1 means
inventory gaps; 2 means invalid input. Every result has
`release_verdict: NOT_EVALUATED`. No exit code is a release acceptance verdict.

Missing literal registration is a review lead, not proof that functionality is
absent or an accepted historical result failed. Dynamic/aliased property calls,
fixture-provided receipts, parametrization and indirect helper registrations
need actual pytest collection/execution and assertion mapping review. Multiple
tests can intentionally contribute to one scenario. A catalog's historical
OBSERVED_PASS does not establish a pass for today's candidate.

A live catalog requirement remains live even without a decorator. Conversely,
an explicitly live test is reported as requiring live evidence even when its
catalog flag is false. Resolve mismatches against the complete source clauses;
never remove a live requirement just to make default CI green.

The inventory neither consumes result receipts nor checks their authenticity,
coverage, compatibility, corpus hashes, live conformance or elapsed trial time.
The [trusted gate evaluator contract](TEST_EXECUTION.md#gate-evaluator-contract)
remains separately required. Do not update phase/gate acceptance from this
static output. Keep original source-bound evidence unchanged.
