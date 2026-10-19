"""Unprivileged storage observations and advice. No cleanup or configuration writes."""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

GIB = 1024**3


class StorageComponent(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    label: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,48}$")
    path: Path


class StorageSettings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)
    schema_version: Literal[1] = 1
    notifications_enabled: bool = False
    filesystem: Path = Path("/")
    warning_percent: int = Field(default=80, ge=1, le=99)
    critical_percent: int = Field(default=90, ge=2, le=100)
    minimum_free_bytes: int = Field(default=20 * GIB, ge=0)
    component_warning_percent: int = Field(default=20, ge=1, le=100)
    growth_warning_bytes: int = Field(default=5 * GIB, ge=1)
    interval_seconds: int = Field(default=300, ge=60, le=86400)
    include_docker: bool = False
    include_timeshift: bool = False
    components: tuple[StorageComponent, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def validate_scope(self) -> StorageSettings:
        if self.warning_percent >= self.critical_percent:
            raise ValueError("storage_threshold_order")
        if any(not path.is_absolute() for path in (self.filesystem, *(item.path for item in self.components))):
            raise ValueError("absolute_storage_paths_required")
        if len({item.label for item in self.components}) != len(self.components):
            raise ValueError("duplicate_component_label")
        return self


@dataclass(frozen=True)
class Capacity:
    status: str
    device: int | None = None
    total_bytes: int | None = None
    used_bytes: int | None = None
    available_bytes: int | None = None
    reserved_bytes: int | None = None
    used_percent: float | None = None


@dataclass(frozen=True)
class ComponentUsage:
    label: str
    status: str
    bytes: int | None
    basis: str
    filesystem_share_percent: float | None = None


@dataclass(frozen=True)
class StorageWarning:
    code: str
    severity: str
    recommendation: str


@dataclass(frozen=True)
class StorageReport:
    observed_at: str
    filesystem: str
    capacity: Capacity
    components: tuple[ComponentUsage, ...]
    timeshift: dict[str, object]
    warnings: tuple[StorageWarning, ...]
    schema_version: int = 1
    permissions: str = "READ_ONLY_UNPRIVILEGED"
    cleanup_authority: str = "NONE"
    limitations: tuple[str, ...] = (
        "Components may overlap; never sum them into exclusive physical usage.",
        "Docker sizes are daemon-wide logical/shared estimates, not Panestria attribution or physical disk shares.",
        "Directory block estimates deduplicate hardlinks within one scan; shared extents can still be counted twice.",
        "Unknown, denied or timed-out measurements are not zero. No contents, credentials or remote service are read.",
        "Warnings offer owner review only; no deletion, pruning, backup changes or scheduled job is installed.",
    )

    def to_json(self) -> str:
        return json.dumps(asdict(self))


def capacity(path: Path) -> Capacity:
    try:
        device, data = path.stat().st_dev, os.statvfs(path)
        total = data.f_blocks * data.f_frsize
        used = (data.f_blocks - data.f_bfree) * data.f_frsize
        available = data.f_bavail * data.f_frsize
        if total <= 0 or used + available <= 0:
            raise ValueError("capacity_unavailable")
        return Capacity(
            "OBSERVED",
            device,
            total,
            used,
            available,
            total - used - available,
            round(100 * used / (used + available), 2),
        )
    except (OSError, ValueError):
        return Capacity("UNKNOWN")


def directory_usage(component: StorageComponent, disk: Capacity) -> ComponentUsage:
    """Only explicitly selected directories. GNU du runs without sudo or symlink traversal."""
    try:
        if component.path.is_symlink() or not component.path.is_dir():
            raise ValueError("directory_unavailable")
        device = component.path.stat().st_dev
        result = subprocess.run(
            [
                "/usr/bin/du",
                "--block-size=1",
                "--summarize",
                "--one-file-system",
                "--no-dereference",
                "--",
                str(component.path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
        # A failed scan can return a partial count. Never promote it to a complete share.
        if result.returncode != 0 or len(result.stdout) > 8192:
            raise ValueError("directory_scan_incomplete")
        size = int(result.stdout.split(b"\t", 1)[0])
        if size < 0:
            raise ValueError("directory_size_invalid")
        share = round(100 * size / disk.total_bytes, 2) if disk.total_bytes and device == disk.device else None
        return ComponentUsage(component.label, "ESTIMATED", size, "ALLOCATED_BLOCKS_ESTIMATE", share)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return ComponentUsage(component.label, "UNKNOWN", None, "DENIED_INCOMPLETE_OR_TIMED_OUT")


def _docker_size(value: str) -> int:
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(B|kB|KB|MB|GB|TB)", value)
    if match is None:
        raise ValueError("docker_size_unavailable")
    factors = {"B": 1, "kB": 1000, "KB": 1000, "MB": 1000**2, "GB": 1000**3, "TB": 1000**4}
    return int(Decimal(match[1]) * factors[match[2]])


def docker_usage() -> tuple[ComponentUsage, ...]:
    try:
        # Pin the local Unix socket: never inherit a remote DOCKER_HOST/context.
        result = subprocess.run(
            ["/usr/bin/docker", "--host", "unix:///var/run/docker.sock", "system", "df", "--format", "{{json .}}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
        if result.returncode != 0 or len(result.stdout) > 16384:
            raise ValueError("docker_usage_unavailable")
        names = {
            "Images": "docker_images",
            "Containers": "docker_containers",
            "Local Volumes": "docker_volumes",
            "Build Cache": "docker_build_cache",
        }
        values = []
        for line in result.stdout.splitlines():
            item = json.loads(line)
            values.append(
                ComponentUsage(
                    names[item["Type"]], "ESTIMATED", _docker_size(item["Size"]), "DAEMON_WIDE_LOGICAL_SHARED_ESTIMATE"
                )
            )
        if len(values) != 4 or len({value.label for value in values}) != 4:
            raise ValueError("docker_usage_incomplete")
        return tuple(values)
    except (OSError, ValueError, TypeError, KeyError, subprocess.TimeoutExpired):
        return (ComponentUsage("docker", "UNKNOWN", None, "LOCAL_DAEMON_UNAVAILABLE"),)


def timeshift_settings(path: Path = Path("/etc/timeshift/timeshift.json")) -> dict[str, object]:
    """Read bounded configuration only; Timeshift commands can mount/write, so never run them."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError("timeshift_configuration_not_regular")
            raw = os.read(descriptor, 16385)
        finally:
            os.close(descriptor)
        if len(raw) > 16384:
            raise ValueError("timeshift_configuration_size")
        data = json.loads(raw)
        schedules: dict[str, bool | None] = {}
        counts: dict[str, int | None] = {}
        for name in ("hourly", "daily", "weekly", "monthly", "boot"):
            value = data.get(f"schedule_{name}")
            schedules[name] = (
                True if value is True or value == "true" else False if value is False or value == "false" else None
            )
            count = str(data.get(f"count_{name}", ""))
            counts[name] = int(count) if re.fullmatch(r"[0-9]{1,3}", count) else None
        return {
            "status": "OBSERVED",
            "schedules": schedules,
            "retention_counts": counts,
            "physical_snapshot_bytes": None,
            "home_inclusion": "REVIEW_EXCLUSIONS_IN_TIMESHIFT",
            "note": "The hourly due-check is not an hourly backup schedule. Counts do not set a byte cap.",
        }
    except (OSError, ValueError, TypeError, AttributeError):
        return {"status": "UNKNOWN", "physical_snapshot_bytes": None}


def inspect_storage(
    settings: StorageSettings, *, expected_write_bytes: int = 0, previous: StorageReport | None = None
) -> StorageReport:
    if expected_write_bytes < 0:
        raise ValueError("negative_expected_write")
    disk = capacity(settings.filesystem)
    components = tuple(directory_usage(item, disk) for item in settings.components)
    if settings.include_docker:
        components += docker_usage()
    backup: dict[str, object] = timeshift_settings() if settings.include_timeshift else {"status": "NOT_REQUESTED"}
    warnings = []
    options = (
        "Keep data and defer large writes; inspect component details; review backup scope/target in Timeshift; "
        "or add/move storage manually. No action is performed. Preserve databases, models and evidence."
    )
    if disk.available_bytes is None or disk.used_percent is None:
        warnings.append(StorageWarning("capacity_unknown", "WARNING", "Recheck access to the selected filesystem."))
    else:
        if disk.used_percent >= settings.critical_percent:
            warnings.append(StorageWarning("disk_critical", "CRITICAL", options))
        elif disk.used_percent >= settings.warning_percent:
            warnings.append(StorageWarning("disk_high", "WARNING", options))
        if disk.available_bytes - expected_write_bytes < settings.minimum_free_bytes:
            warnings.append(StorageWarning("free_reserve_at_risk", "WARNING", options))
        if previous and previous.filesystem == str(settings.filesystem) and previous.capacity.device == disk.device:
            before = previous.capacity.available_bytes
            if before is not None and before - disk.available_bytes >= settings.growth_warning_bytes:
                warnings.append(StorageWarning("rapid_disk_growth", "WARNING", options))
    for item in components:
        if item.status == "UNKNOWN":
            warnings.append(
                StorageWarning(f"{item.label}_unknown", "WARNING", "Usage is unknown; review access locally.")
            )
        if (
            item.filesystem_share_percent is not None
            and item.filesystem_share_percent >= settings.component_warning_percent
        ):
            warnings.append(StorageWarning(f"{item.label}_large", "WARNING", options))
    if settings.include_docker and any(
        item.label.startswith("docker_") and item.bytes and item.bytes >= GIB for item in components
    ):
        warnings.append(
            StorageWarning(
                "docker_review",
                "INFO",
                "Review Docker Desktop or `docker system df -v` locally. Image/build-cache categories may overlap; "
                "Reclaimable does not mean safe to delete. Review unused cache candidates and rebuild costs, "
                "or keep everything and add capacity. Preserve volumes, active containers and offline dependencies.",
            )
        )
    if backup["status"] == "UNKNOWN":
        warnings.append(StorageWarning("timeshift_unknown", "WARNING", "Review Timeshift settings locally."))
    if previous and backup["status"] == previous.timeshift.get("status") == "OBSERVED":
        if any(backup.get(key) != previous.timeshift.get(key) for key in ("schedules", "retention_counts")):
            warnings.append(
                StorageWarning(
                    "backup_policy_changed",
                    "WARNING",
                    "Timeshift schedule or retention changed since the previous sample. "
                    "Review scope and target locally; no author attribution or settings change is inferred.",
                )
            )
    return StorageReport(
        datetime.now(timezone.utc).isoformat(), str(settings.filesystem), disk, components, backup, tuple(warnings)
    )
