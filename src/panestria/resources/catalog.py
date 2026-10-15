"""Pinned capabilities/license and conservative weights + KV + overhead fit."""

from __future__ import annotations

from dataclasses import dataclass

from panestria.contracts.hardware import HardwareManifest


@dataclass(frozen=True)
class ModelCandidate:
    model_ref: str
    weights_gib: float
    kv_gib_per_1024: float
    overhead_gib: float
    capabilities: tuple[str, ...]
    license: str
    source_url: str

    def resident_gib(self, context_tokens: int) -> float:
        if not 512 <= context_tokens <= 4096:
            raise ValueError("context_limit")
        return self.weights_gib + self.kv_gib_per_1024 * context_tokens / 1024 + self.overhead_gib


STEWARD = ModelCandidate(
    "qwen2.5:1.5b-instruct",
    1.0,
    0.1,
    0.7,
    ("chat", "generate"),
    "Apache-2.0",
    "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct",
)


@dataclass(frozen=True)
class Placement:
    state: str
    model_ref: str | None
    resident_estimate_gib: float
    reasons: tuple[str, ...]
    tokens_per_second_measured: float | None = None


def propose(manifest: HardwareManifest, *, pin: ModelCandidate | None = None, context_tokens: int = 2048) -> Placement:
    model = pin or STEWARD
    if not model.license or not model.source_url or "chat" not in model.capabilities:
        raise ValueError("model_metadata_required")
    required = model.resident_gib(context_tokens)
    ram, disk = manifest.ram_available_gib, manifest.disk_free_gib
    if ram is None or disk is None:
        return Placement("UNAVAILABLE", model.model_ref if pin else None, required, ("capacity_unknown",))
    if ram < required + 2.0 or disk < 2.0:
        return Placement("UNAVAILABLE", model.model_ref if pin else None, required, ("foreground_headroom",))
    if manifest.on_ac_power is not True:
        return Placement("UNAVAILABLE", model.model_ref if pin else None, required, ("ac_power_unknown_or_battery",))
    if manifest.thermal_state == "HOT":
        return Placement("UNAVAILABLE", model.model_ref if pin else None, required, ("thermal_pressure",))
    for gpu in manifest.accelerators:
        if gpu.free_gib is not None and gpu.free_gib >= required + 1.0:
            return Placement("GPU_CANDIDATE", model.model_ref, required, ("benchmark_required",))
    return Placement("CPU_CANDIDATE", model.model_ref, required, ("gpu_unavailable_or_pressure", "benchmark_required"))
