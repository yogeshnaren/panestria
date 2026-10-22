"""Owner-host metadata observations, never canonical task or cleanup authority."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, FiniteFloat, StrictInt


class StorageMetadata(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)


class StorageCapacity(StorageMetadata):
    status: Literal["OBSERVED", "UNKNOWN"]
    total_bytes: StrictInt | None = Field(default=None, ge=0)
    used_bytes: StrictInt | None = Field(default=None, ge=0)
    available_bytes: StrictInt | None = Field(default=None, ge=0)
    reserved_bytes: StrictInt | None = Field(default=None, ge=0)
    used_percent: FiniteFloat | None = Field(default=None, ge=0, le=100)


class StorageComponentStatus(StorageMetadata):
    label: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,48}$")
    status: Literal["OBSERVED", "ESTIMATED", "UNKNOWN"]
    bytes: StrictInt | None = Field(default=None, ge=0)
    basis: str = Field(pattern=r"^[A-Z_]{1,64}$")
    filesystem_share_percent: FiniteFloat | None = Field(default=None, ge=0)


class StorageNotice(StorageMetadata):
    code: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    severity: Literal["INFO", "WARNING", "CRITICAL"]
    recommendation: str = Field(min_length=1, max_length=1024)


class StorageStatus(StorageMetadata):
    schema_version: Literal[1] = 1
    owner_id: UUID
    project_id: UUID
    state: Literal["NOT_CONFIGURED", "DISABLED", "COLLECTING", "OBSERVED", "UNAVAILABLE", "STALLED"]
    notifications_enabled: bool | None = None
    observed_at: AwareDatetime | None = None
    capacity: StorageCapacity | None = None
    components: tuple[StorageComponentStatus, ...] = Field(default=(), max_length=12)
    warnings: tuple[StorageNotice, ...] = Field(default=(), max_length=32)
    timeshift_status: Literal["OBSERVED", "UNKNOWN", "NOT_REQUESTED"] = "NOT_REQUESTED"
    timeshift_schedules: dict[Literal["hourly", "daily", "weekly", "monthly", "boot"], bool | None] | None = None
    physical_snapshot_bytes: None = None
    sample_interval_seconds: StrictInt = Field(default=300, ge=60, le=86400)
    next_check_seconds: StrictInt = Field(default=60, ge=1, le=86400)
    reason: Literal[
        "not_configured",
        "disabled",
        "collecting",
        "ready",
        "configuration_changed",
        "probe_unavailable",
        "probe_deadline_exceeded",
        "closed",
    ]
    scope: Literal["OWNER_HOST_METADATA_NOT_PROJECT_ATTRIBUTION"] = "OWNER_HOST_METADATA_NOT_PROJECT_ATTRIBUTION"
    source: Literal["UNPRIVILEGED_LOCAL_READ_ONLY"] = "UNPRIVILEGED_LOCAL_READ_ONLY"
    cleanup_authority: Literal["NONE"] = "NONE"
    acceptance_authority: Literal["NONE"] = "NONE"
    qualification: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"
