# Using this design with Cursor

## Import and context

Open the actual panestria repository in Cursor. In this checkout the design package lives at `docs/`, not `docs/implementation-r0-r3/`. Preserve specification/ and original hashes; source inclusion does not install skills or grant privileges. No GitHub files were pushed by this task.

Read [START_HERE](START_HERE.md), global design/01 through 05 and [AOS-001](plans/AOS-001-implementation-plan.md). Attach exact selected item/prompt as context; a long file existing on disk is not proof the agent read its decisions.

The reference rule is `docs/cursor/rules/panestria-implementation.mdc`. Copying it to `.cursor/rules/panestria-implementation.mdc` is optional; the copy under `docs/` is not an active project rule until that copy is made. [Official Cursor rules](https://cursor.com/docs/rules) documents that format. The short rule supplies persistent coding guidance; detailed files must still be read explicitly.

## First prompt

~~~text
Read docs/START_HERE.md, its design/01 through 05,
plans/AOS-001-implementation-plan.md and cursor/prompts/AOS-001-S1.md.
Inspect current repository/instructions; the recorded main baseline was
4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917. Explain differences.
Implement only AOS-001-S1: one installed src/panestria package, strict settings,
typed health endpoint and meaningful unit fixtures, preserving existing license.
Run implemented checks and report exact changes/results/evidence/limitations.
Do not implement domain workflows or later slices. Stop after this slice.
~~~

## Repeat

1. Select next ready slice from implementation-slices.json; prerequisites need actual code/evidence.
2. Have Cursor inventory files, read the plan/design and identify assertions.
3. Implement one vertical slice with meaningful tests; split if inspected work cannot fit about one developer-day.
4. Run changed/dependency checks; require actual command/report/exit results.
5. Review negative/failure behavior. Fix code or document a scoped mistaken-plan ADR; never disable security checks to turn green.
6. Update assertion→requirement traceability and exact node manifest; leave future/live cases NOT_RUN.
7. At phase promotion run cumulative release-gates.json. Missing/skipped/wrong-version/mock-for-live cannot promote.

Use fresh chats at large item boundaries with exact code/evidence/context. Prompts specify files/test IDs. Native login, paid/provider/live tests and OS provisioning remain actual scoped setup actions; this package contains no API secret provisioning.

## Review prompt

~~~text
Review current slice diff against source requirement IDs, item plan and global
transaction/security/API design. Check concrete negative/failure cases and
scope/epoch/digest guards. List actionable issues with file/line and failing
scenario. Run only implemented scoped synthetic checks. Distinguish PASS,
NOT_RUN, SKIP and UNKNOWN. Do not invent release completion or expand scope.
~~~

## MVP stop

Complete R3 candidate, cumulative tests/six faults, 14-day consented trial and owner MVP acceptance. Use MVP_ACCEPTANCE_CHECKLIST.md. Acceptance does not authorize SOTA; no handoff automatically continues to R4.
