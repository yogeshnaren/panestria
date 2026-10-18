# Implementation progress

Updated 2026-10-18. The owner has authorized implementation through the R3 MVP,
focused task PRs and verified sequential merges. Stop at the real owner trial and
acceptance checkpoint. Revision 3 remains the active plan; R4–R7 are not started.

| Outcome | Actual state | Remaining acceptance work |
| --- | --- | --- |
| R0 durable synthetic kernel | Accepted for its historical candidate; preserved G0 evidence | Do not reopen accepted R0 work |
| R1 offline Ask and hardware runtime | Working local GPU inference; all ten network-disabled Ask questions pass; restart and bounded GPU pressure pass | Reconcile all clauses and qualify the cumulative G1 candidate |
| R1 browser/session access | PR104 merged; revoked sessions clear Ask output and cannot receive cached SSE resync data | Include in the cumulative candidate evaluation |
| R1 one-worker Build | Fixed PUBLIC calculator proposal, sandboxed edits, independent checks and exact merge approval work; registered read-check MCP profile works | Supported native Bash Build workflow and hostile configuration conformance remain unfinished |
| R1 paid SDK compatibility | Deferred by owner; subscription/local-only operation selected | AOS-016-TC04 is not passed. Original required gate manifest remains intact |
| R2 verified Delegate | Source/request/blob components exist; release not accepted | Finish retrieval, isolation, evidence and the end-to-end research outcome |
| R3 complete MVP | Partial components; release not accepted | Finish remaining revision-3 outcomes, multi-worker integration, dashboard, quota/capture, release qualification and genuine owner trial |

## Latest closed blocker

After the workstation restart, the host CUDA probe initializes successfully and
observes one GPU. Five actual live checks pass at clean source
`d1ee854145b8b689f294db5dd59a69be57128589`. Cold inference TTFT is 2.04 s;
warm inference p95 is 0.041 s. All ten offline Ask questions pass quality and
scope checks with warm p95 0.129 s (limit 3 s). The model uses 1.86 GB VRAM.
A bounded 3 GiB pressure allocation makes admission wait, and admission permits
again after release. A real model-container kill is recovered.

The [raw report and limits](../evidence/r1-offline-qualification-2026-10-18/report.json)
preserve the exact source and measurements. Earlier failing evidence is retained.
Instantaneous cgroup memory is not peak memory or process RSS. GPU admission is
not a hardware partition guarantee. These checks do not establish a full G1 pass.

## Next concrete delivery

Complete the supported native Build workflow: model-requested Bash runs only in
the existing secret-free sandbox under current durable task authority. Independent
verification and exact protected merge approval remain controller-owned. Keep the
existing read-only check profile separate. Validate with public synthetic content
and the existing Claude subscription, then close the remaining R1 acceptance gaps.

Progress is measured by usable outcomes and their remaining acceptance clauses,
not the number of commits, PRs or tests. The machine-readable phase and slice
trackers retain IN_PROGRESS where only part of a slice is evidenced; they are
not a percentage-complete estimate.
