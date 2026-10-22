# Required CI, full regression and verified merge reuse

The owner requested fewer low-value/repeated checks. Preserve the highest-value
functional and security checks, rather than optimizing the number of assertions
deleted. All six existing required check names remain: quality, four behavioral
lanes and the aggregate test. Live/owner acceptance is separate.

| Event | What runs |
| --- | --- |
| PR | Required coverage plus conditional regressions for related changes |
| CI policy, migrations, common fixture/lock changes | Full non-live regression |
| Direct/unverified push | Full non-live regression |
| Main merge proven equivalent to a passing PR | Reuse that exact source result; retain the proof; no new test execution |
| Manual workflow | Full by default; required is an explicit option |
| Local `make test` / lane command without profile | Full, as before |

Quality runs first; failures stop expensive behavioral work. The four isolated
behavioral runners then run concurrently. No shared-database pytest parallelism,
new worker image, provider credentials or live calls are introduced. Browser
approval/recovery and current Ask/Build/Delegate/queue/profile flows remain.

The [reviewed policy](ci-regression-policy.json) lists **exact function selectors**
and source watch patterns. It makes 21 old scripted R0 demo/replay functions and
25 repeated per-domain dump/restore/downgrade functions conditional. Those tests
remain in their original files and run when their group changes or full coverage
is selected. Current real DBOS restore/reconnect and encrypted profile/key-rotation
restore remain required, as do tamper, scoped data, approval and process-boundary
tests. Accepted historical R0 evidence is preserved.

Unlisted/new test functions remain required. A deferred file change promotes its
whole group, including new parameters. Migrations/common fixtures/dependency or
CI-policy changes promote both groups. Unknown comparison bases run full.
Stale, duplicate or ambiguous prefix selectors fail visibly; the policy cannot
defer any of the 21 recorded mutation-witness nodes. Those witnesses concern the
historical five-function pilot, not a current whole-system mutation score.

At the recorded source, full collection is2,299 non-live cases and an unchanged
required profile is2,253. Collection is not execution. The remaining cheap
unit/security parameters detect distinct failures and cost little; removing them
would reduce confidence without a meaningful time benefit. No new permanent
test-of-pytest/linter/self-test suite is added.

Each lane retains its JUnit and `ci-SUITE-selection.json`: source commit, comparison
base, policy hash, changed files and every deferred selector/reason. A required
pass does **not** say every full regression or release gate passed. Full/G1/G2/G3
and actual authorized live evidence retain their original requirements.

To run a full local lane (sequentially on one workstation):

```bash
uv run --frozen python tools/ci_tests.py kernel
# Explicit spelling is equivalent:
uv run --frozen python tools/ci_tests.py kernel --profile full
```

To inspect required coverage without executing fixtures:

```bash
uv run --frozen python tools/ci_tests.py kernel \
  --profile required --base FULL_40_CHARACTER_BASE_COMMIT --collect-only
```

After this workflow is merged, GitHub Actions → ci → Run workflow defaults to
full. Or use an existing GitHub login:

```bash
gh workflow run ci.yml --ref YOUR_CANDIDATE_BRANCH --field profile=full
```

Check the actual run SHA; pin the intended candidate before release validation.
Live checks are still excluded and need their existing separate authorization.

## Why a verified main merge can avoid duplicate work

Main currently permits direct pushes, so a merge-looking commit message is
insufficient. The optional proof reads existing GitHub metadata only. It requires
an actual two-parent main merge, a completed successful PR run on that exact
second parent, all six successful jobs, four nonexpired artifacts sharing one
tested preview SHA, and that preview's exact parent list and full tree matching
the pushed merge. Any failed/pending run on that head, failed manual full run or incomplete history
also prevents reuse; it never searches backward for an older green.
Metadata access, parsing, job/artifact, parent or tree uncertainty
runs full checks. The GitHub token has repository contents/actions read scope;
no provider secret is supplied or printed.

The quality job retains `ci-merge-proof.json` and its upstream run/source. Only
that proof permits skipped behavioral jobs in the aggregate. Failed/cancelled/
skipped ordinary verification cannot become green. A reused run is not a new
measurement, live qualification, evidence refresh or release PASS.

The CI-policy PR deliberately runs the full suite once to verify selection and
runner ordering. Prior-run timing projections and manual fault fixtures are
separate from the actual hosted result. See the [source-bound report](../../evidence/ci-required-coverage-2026-10-22/report.json).
