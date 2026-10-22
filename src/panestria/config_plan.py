"""Private operator configuration for an offline, proposal-only local planner."""

import os
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictInt

from panestria.config_local import read_private
from panestria.contracts.model_manifest import ModelManifest


class PlanModelSettings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)
    schema_version: StrictInt
    owner_id: UUID
    project_id: UUID
    model_cache: Path
    runtime_directory: Path
    model_manifest_file: Path | None = None


def expected_plan_manifest(settings: PlanModelSettings) -> ModelManifest | None:
    path = settings.model_manifest_file
    if path is None:
        return None
    if (
        not path.is_absolute() or path.resolve() != path
        or path.is_relative_to(settings.model_cache) or path.is_relative_to(settings.runtime_directory)
    ):
        raise ValueError("plan_model_manifest_path_invalid")
    manifest = ModelManifest.model_validate_json(read_private(path, 8192))
    if manifest.runtime_profile != "CPU_JSON_V1" or manifest.tools or manifest.max_context_tokens < 4096:
        raise ValueError("plan_json_model_manifest_required")
    return manifest


def load_plan_settings(path: Path) -> PlanModelSettings:
    settings = PlanModelSettings.model_validate_json(read_private(path, 8192))
    if settings.schema_version != 1:
        raise ValueError("unsupported_plan_model_settings")
    cache, runtime = settings.model_cache, settings.runtime_directory
    for directory in (cache, runtime):
        if not directory.is_absolute() or directory.resolve() != directory or directory.is_symlink():
            raise ValueError("plan_model_path_invalid")
    if cache.is_relative_to(runtime) or runtime.is_relative_to(cache):
        raise ValueError("plan_model_path_overlap")
    if not cache.is_dir() or {p.name for p in cache.iterdir()} != {"blobs", "manifests"}:
        raise ValueError("dedicated_model_cache_required")
    if runtime.exists() and (
        not runtime.is_dir() or runtime.stat().st_uid != os.getuid() or runtime.stat().st_mode & 0o077
    ):
        raise ValueError("private_plan_model_runtime_required")
    expected_plan_manifest(settings)
    return settings
