"""Explicit private wrapper for existing offline Ask scope and existing OS keys."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictInt, ValidationError, model_validator

from panestria.config_local import LocalApplicationRejected, LocalApplicationSettings, load_local_settings, read_private
from panestria.memory.keys import ProfileKeyHandle


class ProfileServiceSettings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)
    schema_version: StrictInt = Field(ge=1, le=1)
    local_config: Path
    qualification_directory: Path
    qualification_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    key_handles: tuple[ProfileKeyHandle, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def unique(self) -> "ProfileServiceSettings":
        if len({tuple(h.model_dump().values()) for h in self.key_handles}) != len(self.key_handles):
            raise ValueError("duplicate_key_handles")
        return self


def load_profile_service(path: Path) -> tuple[ProfileServiceSettings, LocalApplicationSettings, SecretStr]:
    try:
        config = ProfileServiceSettings.model_validate_json(read_private(path, 24576))
        if any(
            not p.is_absolute() or p.resolve() != p for p in (path, config.local_config, config.qualification_directory)
        ):
            raise ValueError
        local, token = load_local_settings(config.local_config)
        if local.bind_host != "127.0.0.1" or any(
            (h.owner_id, h.project_id) != (str(local.owner_id), str(local.project_id)) for h in config.key_handles
        ):
            raise ValueError
        if any(
            p.is_relative_to(local.model_cache.resolve())
            for p in (path, config.local_config, config.qualification_directory)
        ):
            raise ValueError
        return config, local, token
    except (ValueError, ValidationError):
        raise LocalApplicationRejected("invalid_profile_service_configuration") from None
