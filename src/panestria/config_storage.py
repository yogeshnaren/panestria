"""Read only an explicitly selected private storage-notification configuration."""

from pathlib import Path

from panestria.config_local import LocalApplicationRejected, read_private
from panestria.resources.storage import StorageSettings


def load_storage_settings(path: Path) -> StorageSettings:
    if not path.is_absolute() or path.resolve() != path:
        raise LocalApplicationRejected("storage_configuration_path_invalid")
    return StorageSettings.model_validate_json(read_private(path, 16384))
