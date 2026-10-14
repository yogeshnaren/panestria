# R1 execution control

R0 was accepted by the repository owner and pushed to `origin/r0-kernel` at
`a5b9233`. R1 implementation is authorized on `r1-alpha`. Preserve individual
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
The renewed login check currently returns an account monthly spend-limit error;
no account-limit changes or credential substitution are authorized by that check.

Use disposable R1 test databases on a separate loopback port/container. Preserve
the existing R0 review database, service, evidence and original skill archive.

Applied R0 migrations are immutable. R1 revisions start at 0005, following
0004_check_candidate. Earlier design revision numbers were prospective labels;
implementation uses forward migrations rather than rewriting applied history.

G1 remains incomplete until actual OS, Claude, paid SDK, hardware, local model,
offline and resource-pressure cases pass. No mock substitutes for a live case.
R1 owner review is separate from G1 evidence. R2/R3 implementation is not started.
