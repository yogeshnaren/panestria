# Local model process memory

The physical cold/warm benchmark now records process RSS and PSS separately from
Docker's cgroup working-memory snapshot. `ModelRuntime.process_memory()` validates
the running container's runtime identity, user and private PID namespace before
and after a read-only Python probe. It reads only numeric `Rss`/`Pss` values from
each process's `smaps_rollup`; it does not export argv, environment, maps or tokens.

The [kernel procfs documentation](https://docs.kernel.org/filesystems/proc.html)
describes these memory observations. The probe excludes itself, requires stable
process identities and refuses incomplete observations. RSS sums may count shared
pages repeatedly; PSS apportions shared pages. These are observations across
processes, not one atomic instant, peak memory or the cgroup working-memory value.
They must not be substituted for a cgroup-enforced resource limit.

Run the existing physical benchmark with the cached pinned model and healthy
GPU; no model downloads or provider keys are needed:

```bash
uv run --frozen pytest tests/unit/test_model_process_memory.py \
  tests/unit/test_gpu_startup.py tests/integration/test_local_benchmark.py -q \
  --junitxml=/tmp/panestria-model-memory.xml
```

The benchmark uses only its owned network-disabled model container. Expect a
positive RSS/PSS observation alongside cold/warm TTFT, quality and VRAM. Missing
permissions or changing processes are unavailable; do not replace them with zero.
Keep the original cgroup sample as a separate measurement.

At clean `24c461b873d0f6dbead18ef53ab91cfe1439aeb3`, all 17 selected checks passed.
The actual four-process observation was RSS 925,655,040 bytes and PSS 892,785,664
bytes. Warm TTFT p95 was 0.045 s and GPU model VRAM was 1,864,415,744 bytes. The
[raw source-bound report](../../evidence/r1-model-process-memory-2026-10-18/report.json)
preserves the measurements. This closes the missing process-memory observation
in the benchmark; it does not establish full G1 or owner acceptance.
