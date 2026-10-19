"""Explicit private CPU-only synthesis configuration, without provider credentials."""

import os
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from panestria.config_local import read_private


class SynthesisSettings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)
    schema_version: StrictInt = Field(ge=1, le=1)
    owner_id: UUID
    project_id: UUID
    root: Path
    model_cache: Path
    runtime_directory: Path


def load_synthesis_settings(path: Path, *, need_model: bool = True) -> SynthesisSettings:
    settings = SynthesisSettings.model_validate_json(read_private(path, 8192))
    root, cache, runtime = settings.root, settings.model_cache, settings.runtime_directory
    for directory in (root, cache, runtime):
        if not directory.is_absolute() or directory.resolve() != directory or directory.is_symlink():
            raise ValueError("synthesis_path_invalid")
    if any(a.is_relative_to(b) or b.is_relative_to(a) for a, b in ((root, cache), (runtime, cache), (root, runtime))):
        raise ValueError("synthesis_path_overlap")
    if not root.is_dir() or root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o077:
        raise ValueError("private_research_directory_required")
    if need_model and (not cache.is_dir() or {p.name for p in cache.iterdir()} != {"blobs", "manifests"}):
        raise ValueError("dedicated_model_cache_required")
    if runtime.exists() and (
        not runtime.is_dir() or runtime.stat().st_uid != os.getuid() or runtime.stat().st_mode & 0o077
    ):
        raise ValueError("private_synthesis_runtime_required")
    return settings
