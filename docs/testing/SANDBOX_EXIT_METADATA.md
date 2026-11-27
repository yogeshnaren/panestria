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

## Kernel cgroup OOM count (2026-11-26)

Hosted CI kept failing the AOS-008 memory case about one run in four (for
example run 45953363336: exit137, OOMKilled=false, process_failed after the
bounded re-read). A local reproduction found the cause upstream of Docker's
state. In real memory-limit kills with the case's limits on a loaded
workstation, Docker reported OOMKilled=false and emitted no `oom` event, even
1.5-2 s later, in 6 of 30 and 4 of 30 runs. A host poller read the container's
own cgroup v2 `memory.events` in every run and saw `oom_kill 1`, including in
the four Docker missed. The cgroup was removed a few to tens of milliseconds
after the count appeared, always before `docker start --attach` returned. A
later Docker re-read therefore cannot recover the kill. containerd's cgroup v2
watcher reads `memory.events` only on inotify notifications, which the kernel
limits to one per file per 10 ms. From reading its source (not instrumented),
its forwarding goroutine can also return on the closed error channel while the
final reading is still buffered.

The controller now reads the kernel's `oom_kill` counter from the worker's own
cgroup (`system.slice/docker-<id>.scope` or `docker/<id>` under
`/sys/fs/cgroup`, by full container ID) while the worker runs. It samples every
millisecond while the file is changing. The kernel increments this counter
before signalling the victim, and only the OOM killer increments it. Docker
kill, deadline, cancellation, output/workspace stops and self-SIGKILL leave it
at zero, so those cases keep their reasons. Exit137 alone still proves nothing.
The receipt keeps `oom_killed` as Docker's own flag and records the kernel
count separately as `cgroup_oom_kills`. That field is None when no reading was
made (no host cgroup v2 view, another cgroup layout, or rootless Docker).
Either source gives memory_limit. process_failed remains when neither saw a
kill. This replaces the earlier requirement of an explicit Docker flag for the
real memory cases. Those cases still require memory_limit and record which
source saw the kill.

The read is best effort, not a guarantee: the host thread must run between the
count and the cgroup's removal. Docker's misses depend on host load. During
development, at load averages up to about 90 on 24 CPUs, the production runner
classified all 100 memory kills as memory_limit. Docker missed 2 of them and
the cgroup count caught both. The count missed 1 that Docker caught. With the
count disabled, the same runner reported process_failed for 3 of 40. In the
source-bound batches at lower load, Docker missed 1 of 60 concurrent kills,
and the count still classified it memory_limit. Deadline, cancel and
self-SIGKILL runs kept their reasons with a count of zero.
[Observations and diagnostic scripts](../../evidence/sandbox-cgroup-oom-2026-11-26/report.json)
record the environment and limits. They are local workstation evidence, not
hosted CI or live gate evidence.
