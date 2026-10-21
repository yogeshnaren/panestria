"""Fast opt-in capacity admission. Observes and defers; never cleans up storage."""

from dataclasses import asdict
from typing import Any

from panestria.config_build import BuildSettings
from panestria.config_local import read_private
from panestria.resources.storage import StorageSettings, inspect_storage


def build_storage_admission(settings: BuildSettings) -> dict[str, Any] | None:
    if settings.storage_policy is None:
        return None
    try:
        policy = StorageSettings.model_validate_json(read_private(settings.storage_policy, 16384))
        if not policy.notifications_enabled:
            return None
        # Recheck before each new claim without repeated expensive du/daemon
        # calls. Detailed probes remain the explicit storage inspect command.
        fast = policy.model_copy(update={"components": (), "include_docker": False, "include_timeshift": False})
        report = inspect_storage(fast, expected_write_bytes=settings.anticipated_build_write_bytes)
        codes = {w.code for w in report.warnings}
        reason = "capacity_observed"
        if report.capacity.device is None:
            reason = "storage_capacity_unknown"
        elif report.capacity.device != settings.root.stat().st_dev:
            reason = "storage_policy_filesystem_mismatch"
        elif "disk_critical" in codes:
            reason = "storage_critical"
        elif "free_reserve_at_risk" in codes:
            reason = "storage_reserve_at_risk"
        return {
            "decision": "ALLOW" if reason == "capacity_observed" else "DEFER",
            "reason": reason,
            "anticipated_write_bytes": settings.anticipated_build_write_bytes,
            "basis": "OWNER_CONFIGURED_PLANNING_ESTIMATE_NOT_A_WRITE_CAP_OR_RESERVATION",
            "report": asdict(report),
            "details": "Detailed directory/Docker/Timeshift probes require explicit storage inspect.",
            "cleanup_authority": "NONE",
        }
    except Exception:
        # A configured but unreadable policy never silently disables protection.
        return {"decision": "DEFER", "reason": "storage_policy_unconfirmed", "cleanup_authority": "NONE"}
