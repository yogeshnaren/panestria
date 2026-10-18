# Implementation progress

Updated 2026-10-18. The owner has authorized implementation through the R3 MVP,
focused task PRs and verified sequential merges. Stop at the real owner trial and
acceptance checkpoint. Revision 3 remains the active plan; R4–R7 are not started.

| Outcome | Actual state | Remaining acceptance work |
| --- | --- | --- |
| R0 durable synthetic kernel | Accepted for its historical candidate; preserved G0 evidence | Do not reopen accepted R0 work |
| R1 offline Ask and hardware runtime | Working local GPU inference; all ten network-disabled Ask questions pass; restart and bounded GPU pressure pass | Reconcile all clauses and qualify the cumulative G1 candidate |
| R1 browser/session access | PR104 merged; revoked sessions clear Ask output and cannot receive cached SSE resync data | Include in the cumulative candidate evaluation |
| R1 one-worker Build | Bounded native Bash backend now edits two files, freezes the candidate, runs separate checks and requires exact approval before merge; fixed proposal and read-check profiles retained | Generic owner-project cloud admission/context/certificate integration and cumulative G1 qualification remain |
| R1 paid SDK compatibility | Deferred by owner; subscription/local-only operation selected | AOS-016-TC04 is not passed. Original required gate manifest remains intact |
| R2 verified Delegate | HTTPS fetch, isolated readers and retained source/claim components exist; release not accepted | Connect the components into the verified research workflow and qualify G2 |
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

The subsequent [process-memory qualification](testing/MODEL_PROCESS_MEMORY.md)
records real RSS/PSS separately: four processes, RSS 925,655,040 bytes and PSS
892,785,664 bytes. It closes the benchmark's missing RSS observation while
preserving earlier reports unchanged. It is a snapshot, not peak memory.

## Next concrete delivery

Integrate the qualified Bash backend with admitted owner-project context and the
native-call/runtime certificate boundary, then close remaining R1 acceptance
clauses. The [native Build report](../evidence/r1-native-bash-build-2026-10-18/report.json)
records actual PUBLIC subscription conformance, independent two-file checks and
exact scripted approval. The [test guide](testing/NATIVE_BASH_BUILD.md) explains
how to reproduce it and what is still pending. No generic cloud launch endpoint
is exposed by this backend task.

Progress is measured by usable outcomes and their remaining acceptance clauses,
not the number of commits, PRs or tests. The machine-readable phase and slice
trackers retain IN_PROGRESS where only part of a slice is evidenced; they are
not a percentage-complete estimate.
