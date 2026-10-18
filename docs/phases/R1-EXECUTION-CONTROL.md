# R1 execution control

R0 was accepted by the repository owner and pushed to `origin/r0-kernel` at
`a5b9233`. R1 implementation is authorized. The old `r1-alpha` branch is a preserved historical reference; new task branches start at current main or their explicit unmerged prerequisite. Preserve individual
commits authored by Yogesh Naren Bundey; do not squash or merge main implicitly.

Implement the 13 items and 39 slices in R1-BUILD-PLAN.md, then evaluate all G1
obligations for one recorded candidate. Commit coherent slices with their tests:
leases; effects/outbox; budget/retries; independent policy; OS sandbox; browser
sessions; Claude protocol/profile; verifier/merge; memory; learning; telemetry;
hardware/catalog; local and SDK inference; offline Ask; resource admission.

The owner authorized existing Claude login and existing API credential reuse,
with only synthetic content sent and a total paid SDK test cap of USD 1.
This does not authorize extracting Claude OAuth credentials as API keys or
sending project secrets. Keep API credentials out of workers, Git and reports.

On 2026-10-13 the owner clarified the runtime boundary: local Claude Code with
Anthropic inference is allowed; tasks, approvals and runtime records belong in
Panestria's local UI/CLI and database. The runtime must operate independently of
this development chat. Hold OpenAI live calls and automatic provider fallback;
do not interpret local execution as offline inference. Credentials stay in the
native local authentication store. Remote telemetry is disabled by default.
The historical renewed-login check returned an account spend-limit error;
no account-limit changes or credential substitution are authorized by that check.

Use disposable R1 test databases on a separate loopback port/container. Preserve
the existing R0 review database, service, evidence and original skill archive.

Applied R0 migrations are immutable. R1 revisions start at 0005, following
0004_check_candidate. Earlier design revision numbers were prospective labels;
implementation uses forward migrations rather than rewriting applied history.

G1 remains incomplete until its actual required evidence passes. The owner's
2026-10-18 subscription/local-only decision defers paid SDK AOS-016-TC04; it is
not passed and its original gate requirement remains. OpenAI live calls remain
unauthorized. No mock substitutes for a required live case. R1 owner review is
separate from G1 evidence. R2/R3 components exist; their releases are not accepted.
The current [progress page](../IMPLEMENTATION_PROGRESS.md) and
[owner Build CLI](../testing/OWNER_BUILD_CLI.md) supersede older implementation-status assumptions.

The owner previously expected a quota reset within about 24 hours; this is historical context, not a current usage observation. Keep successful
native inference/conformance cases pending while continuing all independent
local work. This dependency does not suspend R1 implementation or authorize
raising account limits, changing credentials or substituting mocks for live proof.

On 2026-10-14 the owner requested task-based branches and PRs instead of an
aggregate R1 PR. The original `r1-alpha` history is preserved as a reference;
current work is submitted through the [task PR stack](../reviews/R1-TASK-PR-STACK.md).
Use a focused task branch and PR for subsequent changes, preserve author identity
and source-bound evidence, and report pending live checks explicitly.

Revision 3's current build entrypoint is [the phased plan](../PANESTRIA_PHASED_IMPLEMENTATION_PLAN.md). G1 remains NOT_RUN; actual current native eligibility must be rechecked under the existing scoped permissions rather than inferred from an old error/date. New quota-queue, profile and phone requirements are tracked explicitly for R3. This document grants no new model spending or secret access.
