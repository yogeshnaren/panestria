"""Private bounded configuration for the separately launched local Ask process."""

from __future__ import annotations

import os
import re
import secrets
import stat
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictInt, ValidationError


class LocalApplicationRejected(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class LocalApplicationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)
    schema_version: StrictInt = Field(ge=1, le=1)
    owner_id: UUID
    project_id: UUID
    bind_host: Literal["127.0.0.1", "::1"] = "127.0.0.1"
    bind_port: StrictInt = Field(default=8766, ge=1, le=65535)
    token_file: Path
    model_cache: Path
    runtime_directory: Path
    assistant_charter: bool = False

    @property
    def origin(self) -> str:
        host = "[::1]" if self.bind_host == "::1" else self.bind_host
        return f"http://{host}:{self.bind_port}"


def read_private(path: Path, limit: int) -> bytes:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise LocalApplicationRejected("local_file_must_be_private")
            if not 0 < info.st_size <= limit:
                raise LocalApplicationRejected("local_file_size_limit")
            body = os.read(descriptor, limit + 1)
            if len(body) != info.st_size:
                raise LocalApplicationRejected("local_file_size_limit")
            return body
        finally:
            os.close(descriptor)
    except OSError:
        raise LocalApplicationRejected("local_file_unavailable") from None


def load_local_settings(path: Path) -> tuple[LocalApplicationSettings, SecretStr]:
    try:
        config = LocalApplicationSettings.model_validate_json(read_private(path, 8192))
        paths = (config.token_file, config.model_cache, config.runtime_directory)
        if any(not value.is_absolute() or value.is_symlink() for value in paths):
            raise LocalApplicationRejected("local_path_invalid")
        cache, runtime = config.model_cache.resolve(), config.runtime_directory.resolve()
        if cache.is_relative_to(runtime) or runtime.is_relative_to(cache):
            raise LocalApplicationRejected("local_path_overlap")
        if path.resolve().is_relative_to(cache) or config.token_file.resolve().is_relative_to(cache):
            raise LocalApplicationRejected("local_path_overlap")
        # This root is mounted into the model. Reject a home/project or mixed-data
        # directory even if someone has also placed a valid model manifest in it.
        if not cache.is_dir() or {entry.name for entry in cache.iterdir()} != {"blobs", "manifests"}:
            raise LocalApplicationRejected("dedicated_model_cache_required")
        raw = read_private(config.token_file, 256).decode("ascii").strip()
        if re.fullmatch(r"[A-Za-z0-9_-]{32,128}", raw) is None:
            raise LocalApplicationRejected("invalid_local_token")
        return config, SecretStr(raw)
    except (ValidationError, UnicodeDecodeError):
        raise LocalApplicationRejected("invalid_local_configuration") from None
    except OSError:
        raise LocalApplicationRejected("local_file_unavailable") from None


def create_local_token(path: Path) -> None:
    """Explicit local auth setup; never overwrite a token or print its value."""
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            os.write(descriptor, secrets.token_urlsafe(32).encode() + b"\n")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        raise LocalApplicationRejected("local_token_creation_denied") from None
