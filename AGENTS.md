# Repository workflow

- Use a separate `task/<short-name>` branch and PR for each cohesive task or
  independently reviewable acceptance outcome. Do not open a whole milestone
  as one aggregate PR.
- Start from current `main`, or from the explicit prerequisite task branch when
  the work depends on an unmerged PR. Name the prerequisite and review order in
  the PR description. Keep stacked PR diffs limited to their own task.
- Preserve the repository owner's configured Git author identity and existing
  commits. Keep implementation, tests and related corrections in clear commits.
  Do not squash, rewrite published history, or merge PRs without authorization.
- Run the available CI checks before handoff. Distinguish default tests from
  required live validation, and use draft PRs for unfinished implementation.
  A passing component suite does not complete the R1/G1 release gate.
- Preserve original specs, skill attachments and historical evidence. Do not
  relabel evidence for a different source commit.
- Use disposable test database projects and ports. Preserve the owner's review
  database and services. Keep credentials and model caches out of Git.

See [the task PR workflow](docs/TASK_PR_WORKFLOW.md) for commands and review rules.
