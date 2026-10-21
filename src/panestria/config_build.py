"""Private operator configuration, never model-authored Build authority."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from panestria.config_local import read_private
from panestria.verification.registry import CommandRegistry, RegisteredCommand


class BuildCheckSetting(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)
    ref: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    script: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}\.py$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class BuildSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)
    schema_version: int = Field(ge=1, le=1)
    owner_id: UUID
    project_id: UUID
    root: Path
    certificates: Path
    certificate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    native_binary: Path
    native_config: Path
    skills_archive: Path
    checks: list[BuildCheckSetting] = Field(min_length=1, max_length=16)

    storage_policy: Path | None = None
    anticipated_build_write_bytes: int = Field(default=1024**3, ge=1, le=32 * 1024**3)
    record_runtime_metrics: bool = False
    capture_verified_results: bool = False

    @property
    def protected(self) -> Path:
        return self.root / "protected"

    @property
    def repository(self) -> Path:
        return self.protected / str(self.owner_id) / str(self.project_id) / "destination.git"

    def registry(self) -> CommandRegistry:
        directory = self.root / "reviewed"
        _directory(directory)
        if len({check.ref for check in self.checks}) != len(self.checks):
            raise ValueError("duplicate_build_check")
        if {path.name for path in directory.iterdir()} != {check.script for check in self.checks}:
            raise ValueError("dedicated_build_check_directory_required")
        commands = []
        for check in self.checks:
            script = directory / check.script
            raw = read_private(script, 64 * 1024)
            if hashlib.sha256(raw).hexdigest() != check.sha256:
                raise ValueError("reviewed_build_check_changed")
            commands.append(RegisteredCommand(check.ref, ("/reviewed/python", str(script)), True, check.sha256))
        return CommandRegistry(directory, "/reviewed/python", tuple(commands))


def _directory(path: Path) -> None:
    if (
        not path.is_absolute()
        or path.resolve() != path
        or not path.is_dir()
        or path.stat().st_uid != os.getuid()
        or path.stat().st_mode & 0o077
    ):
        raise ValueError("private_build_directory_required")


def load_build_settings(path: Path) -> BuildSettings:
    settings = BuildSettings.model_validate_json(read_private(path, 16 * 1024))
    for directory in (settings.root, settings.certificates, settings.native_config):
        _directory(directory)
    # Credentials/certificates must never sit under a worker-mountable root.
    if any(
        a.is_relative_to(b) or b.is_relative_to(a)
        for a, b in ((settings.native_config, settings.root), (settings.certificates, settings.root))
    ):
        raise ValueError("build_private_path_overlap")
    settings.registry()
    return settings
