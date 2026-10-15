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

## Recorded integration order

The ancestry repair is [PR #33](https://github.com/yogeshnaren/panestria/pull/33).
The previously closed tasks are integrated separately through these follow-ups:

| Original task PR | Follow-up PR targeting main after its prerequisite |
| --- | --- |
| [#4](https://github.com/yogeshnaren/panestria/pull/4) | [#34](https://github.com/yogeshnaren/panestria/pull/34) |
| [#5](https://github.com/yogeshnaren/panestria/pull/5) | [#35](https://github.com/yogeshnaren/panestria/pull/35) |
| [#6](https://github.com/yogeshnaren/panestria/pull/6) | [#36](https://github.com/yogeshnaren/panestria/pull/36) |
| [#7](https://github.com/yogeshnaren/panestria/pull/7) | [#37](https://github.com/yogeshnaren/panestria/pull/37) |
| [#8](https://github.com/yogeshnaren/panestria/pull/8) | [#38](https://github.com/yogeshnaren/panestria/pull/38) |
| [#9](https://github.com/yogeshnaren/panestria/pull/9) | [#39](https://github.com/yogeshnaren/panestria/pull/39) |
| [#10](https://github.com/yogeshnaren/panestria/pull/10) | [#40](https://github.com/yogeshnaren/panestria/pull/40) |
| [#11](https://github.com/yogeshnaren/panestria/pull/11) | [#41](https://github.com/yogeshnaren/panestria/pull/41) |
| [#12](https://github.com/yogeshnaren/panestria/pull/12) | [#42](https://github.com/yogeshnaren/panestria/pull/42) |
| [#13](https://github.com/yogeshnaren/panestria/pull/13) | [#43](https://github.com/yogeshnaren/panestria/pull/43) |
| [#14](https://github.com/yogeshnaren/panestria/pull/14) | [#44](https://github.com/yogeshnaren/panestria/pull/44) |
| [#15](https://github.com/yogeshnaren/panestria/pull/15) | [#45](https://github.com/yogeshnaren/panestria/pull/45) |
| [#16](https://github.com/yogeshnaren/panestria/pull/16) | [#46](https://github.com/yogeshnaren/panestria/pull/46) |
| [#17](https://github.com/yogeshnaren/panestria/pull/17) | [#47](https://github.com/yogeshnaren/panestria/pull/47) |

Then original PRs #18–32 are retargeted to main and merged one at a time, preserving
all original commits. Each actual merge is checked for the expected parent
commits and exact candidate tree. Each task's default CI must pass before its
merge. Main runs the complete default suite after the final integration.

One whitespace-only difference in the Ask test fixture, introduced in the earlier
rebased history, is aligned with original PR #13's reviewed snapshot. No runtime
behavior or original evidence is changed during that reconciliation.

This final integration-record PR targets PR #32 while preparing its CI. It is
retargeted to main and merged only after all task PRs have reached main. Its file
changes are limited to this audit and the review index; runtime code remains the
same as the tested native review demo source `0b6bf40`.

The repository owner authorized these merges. Existing working checkouts, their
untracked runtime files, the running preview, R0 review data, original spec ZIPs,
skills attachments and native credentials are preserved. No live inference is
needed for any integration check. Native quota and live release acceptance remain
separate from implementation integration.
