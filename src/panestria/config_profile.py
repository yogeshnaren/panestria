"""Explicit loopback owner-profile client scope; no service/key/model enablement."""

import re
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictInt, ValidationError

from panestria.config_local import LocalApplicationRejected, read_private


class ProfileClientSettings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)
    schema_version: StrictInt = Field(ge=1, le=1)
    owner_id: UUID
    project_id: UUID
    bind_host: Literal["127.0.0.1"] = "127.0.0.1"
    bind_port: StrictInt = Field(default=8766, ge=1, le=65535)
    token_file: Path

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.bind_port}"


def load_profile_client(path: Path) -> tuple[ProfileClientSettings, SecretStr]:
    try:
        if not path.is_absolute() or path.resolve() != path:
            raise LocalApplicationRejected("profile_client_path_invalid")
        settings = ProfileClientSettings.model_validate_json(read_private(path, 8192))
        token_path = settings.token_file
        if not token_path.is_absolute() or token_path.resolve() != token_path:
            raise LocalApplicationRejected("profile_client_path_invalid")
        token = read_private(token_path, 256).decode("ascii").strip()
        if re.fullmatch(r"[A-Za-z0-9_-]{32,128}", token) is None:
            raise LocalApplicationRejected("invalid_local_token")
        return settings, SecretStr(token)
    except (ValidationError, UnicodeDecodeError):
        raise LocalApplicationRejected("invalid_profile_client_configuration") from None
