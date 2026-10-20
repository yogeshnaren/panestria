# Stopped sandbox exit metadata

Hosted CI39465342810 observed the existing memory-pressure case exit137 with
Docker OOMKilled=false, producing process_failed instead of the case's required
memory_limit. The sandbox source blob was identical in the owner-terminal PR144
and its main base; the new terminal checks passed. The original failed JUnits
remain preserved. This is not permission to accept SIGKILL as an OOM proof.

After a normally observed attach/worker exit137 with no OOM flag, the controller
now briefly re-reads the exact stopped container's daemon metadata: at most four
read-only inspections within a1second window, each bounded to200ms. A later
explicit OOMKilled=true can refine the failed reason to memory_limit. If absent
or unavailable, process_failed remains. Wrong identity, a running/non-exited state
or contradictory exit metadata refuses confirmation. Known controller kills
(deadline/cancellation/output limit) do not enter this extra observation path.
No worker restart, resource widening, global container operation or outcome PASS
is added. Exact owned-container cleanup remains mandatory.

The existing real Docker memory case still requires memory_limit and an explicit
true OOM flag, bounded output/elapsed time and confirmed exact container removal.
It records before/after stopped metadata in JUnit. Real OS-process/pipe cases
separately substitute the daemon-state seam to prove a delayed explicit flag is
observed and an ordinary SIGKILL is never called OOM from its exit code alone.
Those substituted metadata observations do not constitute actual Docker evidence.

[Source-bound observations](../../evidence/sandbox-exit-observation-2026-10-20/report.json)
retain41-case transport checks and three bounded local diagnostics of the exact
memory-pressure case. Local diagnostics all had a real OOM flag already present;
they do not reproduce or prove the hosted failure's cause. The bounded re-read
handles the delayed-observation possibility conservatively. Passing full exact-
head hosted CI is still required before merging this correction or the dependent
terminal feature. Historical failed CI is never relabeled passed.
