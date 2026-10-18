# Implementation progress

Updated 2026-10-18. The owner has authorized implementation through the R3 MVP,
focused task PRs and verified sequential merges. Stop at the real owner trial and
acceptance checkpoint. Revision 3 remains the active plan; R4–R7 are not started.

| Outcome | Actual state | Remaining acceptance work |
| --- | --- | --- |
| R0 durable synthetic kernel | Accepted for its historical candidate; preserved G0 evidence | Do not reopen accepted R0 work |
| R1 offline Ask and hardware runtime | Working local GPU inference; all ten network-disabled Ask questions pass; restart and bounded GPU pressure pass | Reconcile all clauses and qualify the cumulative G1 candidate |
| R1 browser/session access | PR104 merged; revoked sessions clear Ask output and cannot receive cached SSE resync data | Include in the cumulative candidate evaluation |
| R1 one-worker Build | Owner CLI submits selected PUBLIC work through real runtime qualification, admitted Claude/Bash, independent checks, inspection, cancellation and exact protected merge; actual subscription journey passes | Reconcile and qualify the cumulative G1 candidate; human owner review remains |
| R1 paid SDK compatibility | Deferred by owner; subscription/local-only operation selected | AOS-016-TC04 is not passed. Original required gate manifest remains intact |
| R2 verified Delegate | Admitted search and fetch/read/retention now connect to quote checks and private brief inspection under one reviewed policy/certificate; semantic preflights are unqualified | Finish owner new-question orchestration, configure/qualify the real provider/runtime, and qualify support/G2 |
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

Reconcile the remaining R1 gate clauses on one candidate, using the existing
catalog and evidence. The [owner CLI guide](testing/OWNER_BUILD_CLI.md) now provides
a fresh PUBLIC exercise, explicit policy review, submission, diff/check
inspection, exact approval and cancellation. Its actual native journey uses a
real operator-issued runtime certificate; earlier labeled fixture evidence stays
unchanged. The [Bash report](../evidence/r1-native-bash-build-2026-10-18/report.json)
records actual subscription conformance and exact scripted approval. The
[admission guide](testing/ADMITTED_NATIVE_BUILD.md) covers selected source context,
current cloud policy, one-use native launch and cancellation. Its changed-path
native test uses a labeled certificate fixture; it does not certify production.
The [operator qualification command](testing/BUILD_RUNTIME_QUALIFICATION.md)
now issues an expiring runtime-only certificate from actual clean-source
conformance. Its 11 real checks pass, with no fixture certificate. A runtime
certificate grants no project policy. The owner CLI applies only an explicitly
confirmed project grant; the website remains its fixed proposal demo.

Progress is measured by usable outcomes and their remaining acceptance clauses,
not the number of commits, PRs or tests. The machine-readable phase and slice
trackers retain IN_PROGRESS where only part of a slice is evidenced; they are
not a percentage-complete estimate.

The [search transport](testing/CONFIGURED_SEARCH_TRANSPORT.md) adds the missing
configured client. Its real local HTTP fixture checks pass without external
search or provider use. The R2 item/slice tracker now reflects existing component
work as IN_PROGRESS with original source-bound evidence; stale NOT_STARTED flags
must not trigger rebuilding those components. No original result is relabeled,
no entire slice is marked complete and no release is promoted. The next concrete
research task is connecting the bounded workflow. [Durable admission](testing/SEARCH_ADMISSION.md)
now binds the query budget and acknowledged disclosure commit to canonical
owner/task/request policy, lease and deadlines. Concurrency, lost acknowledgement,
cancellation and backup/restore use real disposable Postgres/HTTP fixtures with
explicitly synthetic certificates. No live public-search certificate is issued;
real provider/OS qualification and semantic support remain pending.

PR112 merged after exact-head CI39138503005 passed. Its initial schema snapshot
failure/correction remain source-bound. The owner explicitly deferred search
configuration while independent implementation continues.

The [retained-evidence brief](testing/RETAINED_EVIDENCE_BRIEF.md) connects actual
request/question bytes, current source provenance and deterministic quote checks
to private HTML/JSON export. It shows missing/fabricated evidence and separate
historical/current report hashes, without completing tasks or promoting claims
to supported facts. This inspects existing records; new-request execution,
qualified fetch execution, semantic qualification and full Delegate/G2 remain pending.

The next focused [fetch/read/retention controller](testing/ADMITTED_RESEARCH_FETCH.md)
adds task-wide source/body reservations and committed per-hop disclosure before
DNS, then connects the existing isolated reader and retained source store. Its
component evidence is separate from actual live runtime qualification. New
owner request submission, semantic support and full G2 still remain pending.

PR113 private retained-evidence inspection is merged at04623ee after passing
exact-head CI39156376222. Fetch admission and the joint runtime are subsequent
focused tasks, with original failures/corrections retained separately from
passing evidence.

The [shared research runtime](testing/SHARED_RESEARCH_RUNTIME.md) removes the
policy/certificate incompatibility between search and fetch. Both components
require the explicit joint qualification and its complete report set, while
retaining separate configuration/disclosure hashes and budgets. The connected
actual-DB/loopback/reader fixture produces a retained inspectable brief under
one policy; HTTPS/certificates remain synthetic and semantic support remains
NOT_ASSESSED. Source-bound failure/correction are retained. Next: owner new-question
admission and bounded collection, followed by real runtime/support qualification
when prerequisites are ready. No release gate is promoted.
