# Task branches and pull requests

The owner requested task-based branches and PRs on 2026-10-14. Each PR should
cover one concrete outcome, include its relevant tests, and explain pending
validation. The R0 aggregate PR is already merged; use the task workflow for
current R1 work and subsequent implementation.

For an independent task:

```bash
git fetch origin
git switch -c task/<short-name> origin/main
```

For work that needs an unmerged prerequisite:

```bash
git switch -c task/<short-name> task/<prerequisite>
```

Open its PR against the prerequisite branch. State that dependency and the
merge order in the description. Review and merge the stack from the bottom up;
after merging a prerequisite, retarget the next PR to `main` and check its diff
and CI again. Preserve its ancestry so prerequisite changes disappear from the
next diff. Do not squash a stack: its downstream branches need the original
ancestry. Do not automatically merge or rewrite branches.

Task branches run CI on `pull_request` events. Other branches retain push CI.
This avoids duplicate push and PR runs for each task. CI checks the full
candidate tree, including prerequisites: one quality job and four isolated
behavioral lanes cover the complete non-live suite. The aggregate `test` check
requires every job; JUnit artifacts and slowest-test timings aid diagnosis.
See the [test audit and lane commands](testing/CI_TEST_AUDIT.md). New pushes cancel
obsolete runs for the same PR. Required live/GPU/provider cases remain separate
and must be reported explicitly; default CI is not a release gate substitute.

Preserve the original commits when organizing existing work into task PRs. A
merge from the original development history into a task branch can retain the
source hashes cited by historical evidence while producing a focused diff
against its prerequisite. Do not open another aggregate PR for the reference
development branch. Keep a task-to-PR index for the complete review sequence.
