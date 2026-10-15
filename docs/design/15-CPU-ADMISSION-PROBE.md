# CPU Ask admission without accelerator-tool dependencies

Actual browser qualification on 2026-10-15 completed one local Ask, then the next
request stopped UNAVAILABLE because the hardware probe timed out. Direct timing
showed CPU/RAM/power helpers returning immediately while `probe_nvidia` did not
return. No GPU driver reset or owner application change is authorized by this
failure. Full accelerator qualification remains pending while unavailable.

The supported Ask launcher runs a CPU-only model (no GPU devices/mounts). Add a
Linux `HardwareProbe.collect_cpu` mode that runs the same checksum-gated original
archive with a private empty tool PATH. It still observes actual host CPU, RAM,
available memory, filesystem capacity and AC power; it does not use a preset or
synthetic values. External accelerator helpers cannot be invoked. Mark GPU facts
NOT_PROBED_CPU_ONLY, distinct from observed zero/no GPU. GPU admission still
refuses absent free-VRAM evidence. Preserve the original archive and full probe.

Use this mode only for the new CPU launcher. Admission still requires actual
foreground RAM/disk/power/core headroom on every Ask. Unsupported host or unknown
capacity denies; no automatic fallback. Existing full manifests remain valid.

Bound the probe child using an owned process group and a fixed wait deadline;
discard stdout/stderr that the adapter never uses. On timeout kill only that
group and wait at most one second, rather than an unbounded communicate on pipes
inherited by grandchildren. Kernel-uninterruptible children may remain until the
OS responds; do not claim driver recovery or universal forced erasure. Verify
ordinary sleeping descendants terminate and CPU mode never invokes a GPU helper.
