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

## Active build plan and reuse

- Start with `docs/PANESTRIA_PHASED_IMPLEMENTATION_PLAN.md` (revision 3), its linked active specification and the selected current slice/evidence. Old starter prompts do not reopen accepted R0 work.
- Use the Reverse Engineer Anything (`morluto/rea`) investigation workflow for material borrowing/recreation: inspect complete source directly per its skill, use artifact/runtime analysis when needed, retain pinned evidence/limits/rights and verify the smallest compatible integration. Tool installation or target execution still needs actual task scope; a plan name alone grants neither.
- Basic quota-aware useful work and offline validated-result/eligible-example capture belong to R3. Provider/owner/estimated/unknown observations remain distinct; unknown precision can allow bounded authorized work. Enforce foreground reserves, no-extra-spend eligibility, privacy and independent training-purpose rights.
- A multi-slice MVP goal may continue through authorized ready slices with reviewable task PRs and actual checks. A single-slice request stops there. Do not cross R3 trial/owner acceptance or begin R4-R7 implementation without the corresponding owner decision.
