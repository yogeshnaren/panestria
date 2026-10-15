# R1 task PR review index

Created 2026-10-14. R0 PR #1 is already merged. The remaining development work is organized as 24 R1 task PRs plus one review-workflow PR. All original R1 commits are retained in the stack; their source hashes and historical evidence are preserved.

Review from the first row downward. Each PR targets its prerequisite branch, so its diff shows only its own task. After merging a prerequisite with ancestry preserved, retarget the next PR to `main` and verify its diff and CI again. Do not squash or automatically merge the stack. See [the task workflow](../TASK_PR_WORKFLOW.md).

R1 PRs are drafts because implementation and required live validation remain unfinished. R1 is IN_PROGRESS, G1 is NOT_RUN, and this index does not establish MVP completion. Default CI excludes live provider, GPU and OS conformance cases. Each PR lists its specific remaining work.

| Order | PR | Task | Prerequisite |
| --- | --- | --- | --- |
| 0 | [#2](https://github.com/yogeshnaren/panestria/pull/2) | Use focused task branches and dependency-aware PRs | `main` |
| 1 | [#3](https://github.com/yogeshnaren/panestria/pull/3) | R1 / AOS-006: durable attempts, effect outbox and budgets | [#2](https://github.com/yogeshnaren/panestria/pull/2) |
| 2 | [#4](https://github.com/yogeshnaren/panestria/pull/4) | R1 / AOS-007: independent policy controls and reviewed revisions | [#3](https://github.com/yogeshnaren/panestria/pull/3) |
| 3 | [#5](https://github.com/yogeshnaren/panestria/pull/5) | R1 / AOS-008: inspected worker sandbox and network denial | [#4](https://github.com/yogeshnaren/panestria/pull/4) |
| 4 | [#6](https://github.com/yogeshnaren/panestria/pull/6) | R1 / AOS-009: pairing, scoped browser sessions and CSRF checks | [#5](https://github.com/yogeshnaren/panestria/pull/5) |
| 5 | [#7](https://github.com/yogeshnaren/panestria/pull/7) | R1 / AOS-008 and 016: provider gateway and bounded SDK adapter | [#6](https://github.com/yogeshnaren/panestria/pull/6) |
| 6 | [#8](https://github.com/yogeshnaren/panestria/pull/8) | R1 / AOS-011: scoped memory revisions and provenance-bound context | [#7](https://github.com/yogeshnaren/panestria/pull/7) |
| 7 | [#9](https://github.com/yogeshnaren/panestria/pull/9) | R1 / AOS-015: verified hardware probe and model capacity estimates | [#8](https://github.com/yogeshnaren/panestria/pull/8) |
| 8 | [#10](https://github.com/yogeshnaren/panestria/pull/10) | R1 / AOS-016 and 018: isolated local inference and bounded admission | [#9](https://github.com/yogeshnaren/panestria/pull/9) |
| 9 | [#11](https://github.com/yogeshnaren/panestria/pull/11) | R1 / AOS-017: offline Ask API, CLI and cancellation | [#10](https://github.com/yogeshnaren/panestria/pull/10) |
| 10 | [#12](https://github.com/yogeshnaren/panestria/pull/12) | R1 / AOS-012: explicit routing, exposure and correction records | [#11](https://github.com/yogeshnaren/panestria/pull/11) |
| 11 | [#13](https://github.com/yogeshnaren/panestria/pull/13) | R1 / AOS-014: bounded local traces through durable enqueue | [#12](https://github.com/yogeshnaren/panestria/pull/12) |
| 12 | [#14](https://github.com/yogeshnaren/panestria/pull/14) | R1 / AOS-014: immutable audit events and revocable SSE replay | [#13](https://github.com/yogeshnaren/panestria/pull/13) |
| 13 | [#15](https://github.com/yogeshnaren/panestria/pull/15) | R1 / AOS-007: order policy, task and approval locks consistently | [#14](https://github.com/yogeshnaren/panestria/pull/14) |
| 14 | [#16](https://github.com/yogeshnaren/panestria/pull/16) | R1 / AOS-011: owner memory API and exact privacy reclassification | [#15](https://github.com/yogeshnaren/panestria/pull/15) |
| 15 | [#17](https://github.com/yogeshnaren/panestria/pull/17) | R1 / AOS-018: single primary model and dead-controller recovery | [#16](https://github.com/yogeshnaren/panestria/pull/16) |
| 16 | [#18](https://github.com/yogeshnaren/panestria/pull/18) | R1 / AOS-006: align effect intent and outbox lock ordering | [#17](https://github.com/yogeshnaren/panestria/pull/17) |
| 17 | [#19](https://github.com/yogeshnaren/panestria/pull/19) | R1 / AOS-027a: readonly verifier and attributable protected Git effects | [#18](https://github.com/yogeshnaren/panestria/pull/18) |
| 18 | [#20](https://github.com/yogeshnaren/panestria/pull/20) | R1 / AOS-010: validate native streams and bound cancellation | [#19](https://github.com/yogeshnaren/panestria/pull/19) |
| 19 | [#21](https://github.com/yogeshnaren/panestria/pull/21) | R1 / AOS-027a: freeze Git candidates and bind evidence identities | [#20](https://github.com/yogeshnaren/panestria/pull/20) |
| 20 | [#22](https://github.com/yogeshnaren/panestria/pull/22) | R1 / AOS-027a: publish independent evidence and authorize exact merges | [#21](https://github.com/yogeshnaren/panestria/pull/21) |
| 21 | [#23](https://github.com/yogeshnaren/panestria/pull/23) | R1 / AOS-011: prove memory lineage survives PostgreSQL restore | [#22](https://github.com/yogeshnaren/panestria/pull/22) |
| 22 | [#24](https://github.com/yogeshnaren/panestria/pull/24) | R1 / AOS-007: revoke approvals while preserving original decisions | [#23](https://github.com/yogeshnaren/panestria/pull/23) |
| 23 | [#25](https://github.com/yogeshnaren/panestria/pull/25) | R1 / AOS-027a: scope protected repositories and resume confirmed effects | [#24](https://github.com/yogeshnaren/panestria/pull/24) |
| 24 | [#26](https://github.com/yogeshnaren/panestria/pull/26) | R1: retain development evidence and index task PRs | [#25](https://github.com/yogeshnaren/panestria/pull/25) |

## Source preservation

The original reference branch `r1-alpha` remains at `4ed817c`. Its full history is reachable from the final task branch, including the source `ddd1041` used for the retained local evidence. The initial extraction verified that runtime code, migrations, dependencies, contract snapshots and original specifications matched that reference. The merged R0 CI fixes and regression-stack cleanup are carried forward. Any subsequent CI corrections belong in their affected task PRs as separate commits.

Stored local reports under `evidence/R1-local-continuation/` retain their original candidate hashes. Do not interpret them as results for a different task branch head. Check each PR’s current GitHub Actions result for its full default candidate suite.
