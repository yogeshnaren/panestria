"""Private owner-selected research runtime; configuration never grants permission."""

import os
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from panestria.config_local import read_private
from panestria.contracts.search import LocalSearchSettings


class ResearchSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)
    schema_version: StrictInt = Field(ge=1, le=1)
    owner_id: UUID
    project_id: UUID
    root: Path
    certificates: Path
    certificate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    search: LocalSearchSettings


def validate_research_settings(settings: ResearchSettings) -> ResearchSettings:
    settings = ResearchSettings.model_validate_json(settings.model_dump_json())
    for path in (settings.root, settings.certificates):
        if (
            not path.is_absolute()
            or path.resolve(strict=True) != path
            or not path.is_dir()
            or path.stat().st_uid != os.getuid()
            or path.stat().st_mode & 0o077
        ):
            raise ValueError("private_research_directory_required")
    if settings.root.is_relative_to(settings.certificates) or settings.certificates.is_relative_to(settings.root):
        raise ValueError("research_certificate_store_must_be_separate")
    return settings


def load_research_settings(path: Path) -> ResearchSettings:
    return validate_research_settings(ResearchSettings.model_validate_json(read_private(path, 16 * 1024)))
