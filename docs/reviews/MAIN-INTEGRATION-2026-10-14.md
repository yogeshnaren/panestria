# Main integration audit

The owner authorized sequential integration of the pending task PRs on
2026-10-14. The initial remote `main` was
`f963869b83a024c65cfec00a9ab9cfaef466a072`.

PRs #3–17 were marked merged, but most targeted predecessor task branches.
PR #2 also rebased the foundation while merging it into main. The initial main
file tree was identical to original PR #3 head
`558be0577146801a5f2b1a75a7c3376bab94a9e6`, but the original source commits were
not ancestors of main. This broke the intended ancestry for the later stack.

The repair restores the original foundation ancestry without changing its
runtime tree. Separate follow-up PRs integrate each already-closed task #4–17.
Only after those prerequisites reach main should open task PRs #18–32 be
retargeted and merged there, in dependency order. Original heads are used instead
of predecessor branches that have since accumulated later work. No history is
squashed, rebased, force-pushed or discarded during this repair.

For every step, verify the task diff, the tested source/check result, and the
candidate file tree against its intended source. A retargeted candidate must
retain the tested runtime tree; any content difference requires new validation.
The complete final main tree must pass CI. Retain the individual merge commits
and the original source hashes cited by historical evidence.

Merging implementation does not complete release acceptance: R1 remains
IN_PROGRESS and G1 remains NOT_RUN until its required live checks and owner
acceptance are recorded. No provider calls, credentials, runtime certificates,
review databases or model caches are needed for this integration.
