"""Explicit public model expectations; read only while preparing new local work."""

from pathlib import Path

from panestria.config_local import read_private
from panestria.contracts.model_manifest import ModelManifest


def expected_json_manifest(path: Path | None, cache: Path, runtime: Path) -> ModelManifest | None:
    if path is None:
        return None
    if not path.is_absolute() or path.resolve() != path or path.is_relative_to(cache) or path.is_relative_to(runtime):
        raise ValueError("local_model_manifest_path_invalid")
    manifest = ModelManifest.model_validate_json(read_private(path, 8192))
    if manifest.runtime_profile != "CPU_JSON_V1" or manifest.tools or manifest.max_context_tokens < 4096:
        raise ValueError("local_json_model_manifest_required")
    return manifest
