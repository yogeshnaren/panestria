"""Private loopback metadata settings, independent of model caches and policy grants."""

import os
import re
import stat
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictInt, ValidationError

from panestria.config_local import LocalApplicationRejected, read_private


class ActivitySettings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)
    schema_version: StrictInt = Field(ge=1, le=1)
    owner_id: UUID
    project_id: UUID
    bind_port: StrictInt = Field(default=8769, ge=1, le=65535)
    token_file: Path

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.bind_port}"


def load_activity_settings(path: Path) -> tuple[ActivitySettings, SecretStr]:
    try:
        if not path.is_absolute() or path.resolve() != path:
            raise LocalApplicationRejected("activity_configuration_path_invalid")
        directory = path.parent.stat()
        if not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.getuid() or directory.st_mode & 0o077:
            raise LocalApplicationRejected("local_directory_must_be_private")
        config = ActivitySettings.model_validate_json(read_private(path, 8192))
        if config.token_file != path.parent / "activity.token":
            raise LocalApplicationRejected("activity_token_path_invalid")
        token = read_private(config.token_file, 256).decode("ascii").strip()
        if re.fullmatch(r"[A-Za-z0-9_-]{32,128}", token) is None:
            raise LocalApplicationRejected("invalid_local_token")
        return config, SecretStr(token)
    except (ValidationError, UnicodeDecodeError):
        raise LocalApplicationRejected("invalid_activity_configuration") from None
    except OSError:
        raise LocalApplicationRejected("local_file_unavailable") from None
