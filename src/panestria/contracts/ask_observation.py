"""Schema for existing v1 Ask observations, not an inference or retention grant."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue

from panestria.contracts.model_manifest import ModelManifest
from panestria.contracts.policy import DataLabel


class AskReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request_id: str
    state: Literal["PREPARED", "RUNNING", "COMPLETED", "CANCELLED", "UNAVAILABLE"]
    model_ref: str
    context_pack_id: str
    trace_id: str
    usage: dict[str, JsonValue] | None
    code: str | None
    response_sha256: str | None
    privacy_label: DataLabel
    sources: list[dict[str, JsonValue]]
    response_retained: Literal[False]
    offline: Literal[True]
    response_digest_mode: str | None = None
    profile_context: dict[str, JsonValue] | None = None
    model_manifest: ModelManifest | None = None


class AskAnswer(AskReceipt):
    text: str | None = None
    replayed_receipt: bool = False


class AskCancellation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request_id: str
    state: Literal["PREPARED", "RUNNING", "COMPLETED", "CANCELLED", "UNAVAILABLE"]
