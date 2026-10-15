# Using this design with Cursor

## Import and context

Open the actual panestria repository in Cursor. In this checkout the design package lives at `docs/`, not `docs/implementation-r0-r3/`. Preserve specification/ and original hashes; source inclusion does not install skills or grant privileges. The active planning baseline is revision 3; the original planning-task publication statement is historical.

Read [the main phased plan](PANESTRIA_PHASED_IMPLEMENTATION_PLAN.md), [revision-3 contracts](specification/architecture/05-PERSONAL-PLATFORM-REVISION-3.md), [START_HERE](START_HERE.md), relevant global design/01 through 05 and the selected unfinished AOS/extension plan. Attach exact selected item/prompt as context; a long file existing on disk is not proof the agent read its decisions.

The reference rule is `docs/cursor/rules/panestria-implementation.mdc`. Copying it to `.cursor/rules/panestria-implementation.mdc` is optional; the copy under `docs/` is not an active project rule until that copy is made. [Official Cursor rules](https://cursor.com/docs/rules) documents that format. The short rule supplies persistent coding guidance; detailed files must still be read explicitly.

## First prompt

~~~text
Read AGENTS.md and docs/PANESTRIA_PHASED_IMPLEMENTATION_PLAN.md (revision 3),
docs/specification/architecture/05-PERSONAL-PLATFORM-REVISION-3.md,
docs/phase-tracker.json and the selected entry in docs/implementation-slices.json.
Inspect current main, applicable design/ADR, dependency code and source-bound evidence.
R0 is accepted; do not restart AOS-001-S1 because of historical starter prompts.
Choose only an unfinished slice within this task's authorized phase/goal scope.
For a revision-3 extension use docs/cursor/prompts/MVP-REV3-SLICE.md.
Make a focused task branch/PR, preserve owner authorship and coherent commits,
implement the bounded outcome and run meaningful applicable checks.
Report actual evidence, pending live work and rollback. Continue to another
ready slice only when the user explicitly authorized a multi-slice goal.
Finish the expanded 157-case G3 gate/trial/owner acceptance before R4;
SOTA implementation requires a separate owner decision.
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

## Revision 3 scope rules

The catalogs contain 93 original plus 21 extension envelopes and 157 cumulative G3 cases. New R3 extensions under a parent that originally ships in R1 do not silently reopen G0 or move all parent cases into G1. Use the registered delivery phase/cases. Apply the REA investigation workflow for material reuse/recreation; direct source inspection remains appropriate when the source is complete. A quota balance can be provider/owner-reported, estimated or unknown; authorized bounded useful work does not require invented precision. Training-purpose eligibility and no-extra-spend eligibility are separate gates.
