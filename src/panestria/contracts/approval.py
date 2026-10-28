"""Canonical approval preview. The only fingerprint is effect_digest."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

_HEX = r"^[0-9a-f]{64}$"
_UUID = r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
_WHEN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?\+00:00$")


class PreviewRejected(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ActionPreview(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    action_kind: Literal["contract_consent", "merge", "finalize"]
    owner_id: str = Field(pattern=_UUID)
    project_id: str = Field(pattern=_UUID)
    task_id: str = Field(pattern=_UUID)
    contract_sha256: str = Field(pattern=_HEX)
    contract_version: int = Field(ge=1)
    policy_version: str = Field(min_length=1, max_length=128)
    destination: str = Field(min_length=1, max_length=512)
    expected_base: str = Field(min_length=1, max_length=128)
    candidate_sha256: str = Field(pattern=_HEX)
    required_checks: list[str] = Field(min_length=1)
    minimum_actor_id: str = Field(pattern=_UUID)
    expires_at: str = Field(pattern=_WHEN)

    @model_validator(mode="after")
    def _checks(self) -> Self:
        if len(set(self.required_checks)) != len(self.required_checks):
            raise ValueError("invalid_preview")
        if any(item == "" for item in self.required_checks):
            raise ValueError("invalid_preview")
        return self


def load_preview(data: object) -> ActionPreview:
    """Validate a preview. Failures omit the submitted document."""
    try:
        if not isinstance(data, dict):
            raise PreviewRejected("invalid_preview")
        loaded = ActionPreview.model_validate(data)
    except (PreviewRejected, ValidationError) as exc:
        raise PreviewRejected("invalid_preview") from exc
    canonical = loaded.model_copy(update={"required_checks": sorted(loaded.required_checks)})
    return canonical


# A new request may not outlive this; stored previews keep loading unchanged.
MAX_REQUEST_TTL = timedelta(days=366)


def require_request_bounds(preview: ActionPreview, now: datetime) -> None:
    """Bounds checked when an approval is requested, not when a stored preview is read.

    The owner reviews ``destination`` verbatim, so it must be printable ASCII with
    no whitespace (no homoglyphs, line breaks or trailing spaces). ``expires_at``
    must be a real instant no more than ``MAX_REQUEST_TTL`` ahead.
    """
    if re.fullmatch(r"[\x21-\x7e]+", preview.destination) is None:
        raise PreviewRejected("invalid_preview_destination")
    try:
        expires = datetime.fromisoformat(preview.expires_at)
    except ValueError:
        raise PreviewRejected("invalid_preview_expiry") from None
    if expires > now + MAX_REQUEST_TTL:
        raise PreviewRejected("invalid_preview_expiry")


def effect_digest(preview: ActionPreview) -> str:
    """SHA-256 of canonical UTF-8 JSON. Arrays keep the stored check order."""
    payload = json.loads(preview.model_dump_json())
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
