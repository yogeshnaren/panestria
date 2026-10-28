"""Original selected PUBLIC context metadata; no model, filesystem or task authority."""

import hashlib
import json
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from panestria.contracts.plan import PlanId, Ref

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


def context_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not 1 <= len(value.encode()) <= 16384
        or not path.parts
        or path.is_absolute()
        or path.as_posix() != value
        or any(
            p in {".", "..", ".git", ".ssh", ".aws", ".claude", "secrets"} or p.startswith(".env") for p in path.parts
        )
        or any(ord(c) < 32 for c in value)
        or "\\" in value
        or path.name == ".mcp.json"
    ):
        raise ValueError("invalid_selected_context_path")
    return value


class ClosedContext(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)


class ContextAssignment(ClosedContext):
    task_id: PlanId
    paths: tuple[str, ...] = Field(min_length=1, max_length=32)
    acceptance_keys: tuple[str, ...] = Field(min_length=1, max_length=100)
    expected_artifacts: tuple[Ref, ...] = Field(min_length=1, max_length=8)
    rule: str = Field(min_length=1, max_length=512)

    @field_validator("paths")
    @classmethod
    def literal_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for path in value:
            context_path(path)
        if len(set(value)) != len(value):
            raise ValueError("duplicate_selected_context_path")
        return value


class ContextHeader(ClosedContext):
    intent: str = Field(min_length=1, max_length=16384)
    source_tree: str = Field(pattern=r"^[0-9a-f]{40}$")
    goal_intent_for_reference: str | None = Field(
        default=None, max_length=16384, exclude_if=lambda value: value is None
    )
    assignment: ContextAssignment | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def paired_plan_fields(self) -> Self:
        if (self.assignment is None) != (self.goal_intent_for_reference is None):
            raise ValueError("incomplete_selected_context_assignment")
        return self


class ContextFile(ClosedContext):
    path: str
    sha256: Digest
    size_bytes: StrictInt = Field(ge=0, le=16384)

    @field_validator("path")
    @classmethod
    def literal_path(cls, value: str) -> str:
        return context_path(value)


class NativeContextManifest(ClosedContext):
    schema_version: StrictInt = Field(default=1, ge=1, le=1)
    header: ContextHeader
    files: tuple[ContextFile, ...] = Field(max_length=16)

    @model_validator(mode="after")
    def unique_files(self) -> Self:
        if len({f.path for f in self.files}) != len(self.files):
            raise ValueError("duplicate_selected_context_path")
        if len(self.model_dump_json().encode()) > 32768:
            raise ValueError("selected_context_manifest_limit")
        return self

    @classmethod
    def from_context(cls, context: str) -> Self:
        if len(context.encode()) > 16384:
            raise ValueError("selected_context_limit")
        body = json.loads(context)
        if type(body) is not dict or type(body.get("files")) is not list:
            raise ValueError("invalid_selected_context")
        contents, files = {}, []
        for entry in body["files"]:
            if type(entry) is not dict or set(entry) != {"path", "sha256", "content"}:
                raise ValueError("invalid_selected_context_file")
            if type(entry["content"]) is not str or type(entry["path"]) is not str:
                raise ValueError("invalid_selected_context_file")
            raw = entry["content"].encode()
            contents[entry["path"]] = raw
            files.append({"path": entry["path"], "sha256": entry["sha256"], "size_bytes": len(raw)})
        manifest = cls.model_validate_json(
            json.dumps({"schema_version": 1, "header": {k: v for k, v in body.items() if k != "files"}, "files": files})
        )
        if manifest.render(contents) != context.encode():
            raise ValueError("selected_context_not_canonical")
        return manifest

    def render(self, contents: Mapping[str, bytes]) -> bytes:
        if set(contents) != {f.path for f in self.files}:
            raise ValueError("selected_context_files_mismatch")
        files = []
        for entry in self.files:
            raw = contents[entry.path]
            if (
                type(raw) is not bytes
                or len(raw) != entry.size_bytes
                or hashlib.sha256(raw).hexdigest() != entry.sha256
            ):
                raise ValueError("selected_context_file_mismatch")
            files.append({"path": entry.path, "sha256": entry.sha256, "content": raw.decode("utf-8")})
        raw = json.dumps(
            {**self.header.model_dump(mode="json"), "files": files},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode()
        if len(raw) > 16384:
            raise ValueError("selected_context_limit")
        return raw
