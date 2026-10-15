# Revision 3 extension slice handoff

Use this shared prompt with **one exact extension slice ID** from `docs/implementation-slices.json`. The recorded 21 new envelopes target roughly one developer-day each; split after inspecting code if necessary. This prompt does not authorize the full extension or a later release.

```text
Read AGENTS.md, docs/PANESTRIA_PHASED_IMPLEMENTATION_PLAN.md,
docs/specification/architecture/05-PERSONAL-PLATFORM-REVISION-3.md,
docs/specification/COMMON-REQUIREMENTS.md and the selected slice entry from
docs/implementation-slices.json. Read its owning AOS plan, required case entries
in docs/testing/test-catalog.json and applicable design files/ADR 0003.

Implement only the exact slice selected in the task. Inspect current main,
dependency code and evidence; proposed file paths are ownership candidates.
Distinguish existing implementation from missing code and pending live proof.
Keep historical evidence and applied migrations unchanged. Scope schema,
crypto, provider, grant, transport and approval work with full failure analysis.
Narrow or split the slice before implementing unrelated work.

Create a focused task branch/PR from main or its explicit unmerged prerequisite.
Preserve the owner's author identity and clear implementation/test commits.
Use the REA investigation workflow for material reuse/recreation decisions:
source inspection for complete repositories, appropriate artifact/runtime
analysis when needed, pinned evidence and tested minimal integration.
Do not install tools or execute inspected targets merely because a plan names them.

Run meaningful scoped unit/contract/failure checks and applicable real disposable
PostgreSQL/OS integration. Register actual assertions/node IDs, lane,
gate_case_id, candidate/runtime/hardware/corpus identity and observed evidence.
Default CI cannot replace required live qualification. No credentials are in
this prompt; use existing scoped session authorization, and keep account
provisioning/provider/OS actions within their explicitly authorized bounds.

Quota uncertainty is labeled, not invented: owner-reported observations and
authorized bounded best-effort work are supported. Preserve foreground reserves,
separate no-extra-spend eligibility from quota estimates, and separate ordinary
offline knowledge retention from verified training-purpose eligibility.

Report changes, actual tests, unfinished/live obligations, operational impact
and rollback. Update the slice/requirement evidence without claiming completion
for absent cases. Stop after this slice. G3 requires all 157 registered cases,
the 14-day owner trial and owner acceptance; do not continue to R4 automatically.
```
