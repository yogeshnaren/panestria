"""Versioned observations separate measured capacity from illustrative estimates."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Accelerator(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    vendor: str
    name: str
    total_gib: float | None = Field(default=None, gt=0)
    free_gib: float | None = Field(default=None, ge=0)
    driver: str | None = None
    bandwidth_estimate_gbs: float | None = None
    bandwidth_measured_gbs: float | None = None


class HardwareManifest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    observed_at: datetime
    simulated: bool
    preset: str | None = None
    os: str
    arch: str
    kernel: str
    cpu: str
    logical_cores: int | None = Field(default=None, gt=0)
    ram_total_gib: float | None = Field(default=None, gt=0)
    ram_available_gib: float | None = Field(default=None, ge=0)
    disk_free_gib: float | None = Field(default=None, ge=0)
    accelerators: tuple[Accelerator, ...]
    on_ac_power: bool | None = None
    thermal_state: Literal["UNKNOWN", "NORMAL", "HOT"] = "UNKNOWN"
    permissions: Literal["READ_ONLY_UNPRIVILEGED"] = "READ_ONLY_UNPRIVILEGED"
    gpu_status: Literal["OBSERVED", "NONE_OR_UNSUPPORTED"]
    probe_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    catalog_version: str
    source_license: Literal["NOT_DECLARED_IN_ATTACHED_ARCHIVE"] = "NOT_DECLARED_IN_ATTACHED_ARCHIVE"
