"""Application-owned model identity; no prompt, private profile or readiness grant."""

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class ModelManifest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    model_ref: str = Field(min_length=1, max_length=128)
    model_bundle_sha256: Digest
    weights_sha256: Digest
    # The tokenizer is inside GGUF. Its containing artifact is identified exactly;
    # no separately extracted tokenizer identity or cross-model equivalence claimed.
    tokenizer_container_sha256: Digest
    tokenizer_identity: Literal["GGUF_CONTAINER_NOT_SEPARATELY_EXTRACTED"] = "GGUF_CONTAINER_NOT_SEPARATELY_EXTRACTED"
    template_sha256: Digest
    system_sha256: Digest
    quantization: str = Field(min_length=1, max_length=64)
    runtime_image: str = Field(pattern=r"^[a-z0-9]+@sha256:[0-9a-f]{64}$")
    engine_sha256: Digest
    libraries_sha256: Digest
    bridge_sha256: Digest
    runtime_profile: Literal["CPU_RAW_TEXT_V1", "CPU_JSON_V1"] = "CPU_RAW_TEXT_V1"
    modalities: tuple[Literal["TEXT"]] = ("TEXT",)
    tools: tuple[str, ...] = Field(default=(), max_length=16)
    max_context_tokens: int = Field(default=4096, ge=512, le=4096)
    token_bound: Literal["UTF8_BYTES_WITH_OUTPUT_RESERVE_V1"] = "UTF8_BYTES_WITH_OUTPUT_RESERVE_V1"
    generation: Literal["TEMPERATURE_0_SEED_7_THREADS_2_V1"] = "TEMPERATURE_0_SEED_7_THREADS_2_V1"
    capacity_ref: Literal["LOCAL_PRIMARY_2CPU_2560MIB_FOREGROUND_RECHECK_V1"] = (
        "LOCAL_PRIMARY_2CPU_2560MIB_FOREGROUND_RECHECK_V1"
    )
    license_refs: tuple[Digest, ...] = Field(min_length=1, max_length=8)
    evaluation: Literal["NOT_EVALUATED"] = "NOT_EVALUATED"

    @field_validator("schema_version", mode="before")
    @classmethod
    def explicit_version(cls, value: object) -> object:
        if type(value) is not int or value != 1:
            raise ValueError("invalid_model_manifest_version")
        return value

    def sha256(self) -> str:
        return hashlib.sha256(
            json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def for_json_output(self) -> "ModelManifest":
        """Derive a format expectation; this grants no fresh runtime qualification."""
        return self.model_copy(update={"runtime_profile": "CPU_JSON_V1"})

    def context_compatible(self, other: "ModelManifest") -> bool:
        """Conservative reconstruction compatibility, never permission to repin.

        A different runtime/weight identity still requires its own exact request
        binding. Unknown tokenizer equivalence is incompatible, not guessed.
        """
        names = (
            "tokenizer_container_sha256",
            "tokenizer_identity",
            "template_sha256",
            "system_sha256",
            "quantization",
            "runtime_profile",
            "modalities",
            "tools",
            "max_context_tokens",
            "token_bound",
        )
        return all(getattr(self, name) == getattr(other, name) for name in names)
