"""Pinned, bounded container profiles constructed by the trusted supervisor."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

DEFAULT_IMAGE = "python@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9"
# Total bytes a writable workspace may hold, and the per-file size limit.
DEFAULT_WORKSPACE_BYTES = 1024**3


class SandboxRejected(Exception):
    pass


@dataclass(frozen=True)
class SandboxProfile:
    name: Literal["mock-no-network", "read-only-research", "scoped-code-edit", "restricted-offline"] = (
        "scoped-code-edit"
    )
    image: str = DEFAULT_IMAGE
    uid: int = 1000
    gid: int = 1000
    memory_bytes: int = 256 * 1024 * 1024
    cpu_nanos: int = 500_000_000
    pids: int = 32
    wall_seconds: float = 30
    output_bytes: int = 128 * 1024
    tmp_bytes: int = 32 * 1024 * 1024
    stdin_mode: Literal["closed", "native-frame-v1"] = "closed"
    workspace_bytes: int = DEFAULT_WORKSPACE_BYTES

    @property
    def workspace_readonly(self) -> bool:
        return self.name in {"read-only-research", "restricted-offline"}

    def validate(self) -> None:
        if type(self.stdin_mode) is not str or self.stdin_mode not in ("closed", "native-frame-v1"):
            raise SandboxRejected("unknown_stdin_mode")
        if self.name not in {"mock-no-network", "read-only-research", "scoped-code-edit", "restricted-offline"}:
            raise SandboxRejected("unknown_profile")
        if re.fullmatch(r"[a-zA-Z0-9./_-]+@sha256:[0-9a-f]{64}", self.image) is None:
            raise SandboxRejected("unpinned_image")
        if not 1 <= self.uid <= 65535 or not 1 <= self.gid <= 65535:
            raise SandboxRejected("root_user_denied")
        if not 64 * 1024**2 <= self.memory_bytes <= 8 * 1024**3:
            raise SandboxRejected("invalid_memory_cap")
        if not 100_000_000 <= self.cpu_nanos <= 4_000_000_000 or not 8 <= self.pids <= 256:
            raise SandboxRejected("invalid_process_cap")
        if not 0.1 <= self.wall_seconds <= 900 or not 1024 <= self.output_bytes <= 2 * 1024**2:
            raise SandboxRejected("invalid_output_deadline")
        if not 1024**2 <= self.tmp_bytes <= 256 * 1024**2:
            raise SandboxRejected("invalid_tmp_cap")
        if type(self.workspace_bytes) is not int or not 1024**2 <= self.workspace_bytes <= 16 * 1024**3:
            raise SandboxRejected("invalid_workspace_cap")

    def sha256(self) -> str:
        body = asdict(self)
        # Preserve historical closed-input identities. Opening stdin is an
        # explicit new profile binding, never a widening under an old digest.
        if self.stdin_mode == "closed":
            del body["stdin_mode"]
        # The default quota narrows, never widens, an existing identity.
        if self.workspace_bytes == DEFAULT_WORKSPACE_BYTES:
            del body["workspace_bytes"]
        return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class ReadOnlyMount:
    source: Path
    destination: str

    def validate(self) -> None:
        if self.source.is_symlink() or not self.source.exists() or "," in str(self.source):
            raise SandboxRejected("invalid_runtime_mount")
        if not self.destination.startswith("/runtime/") or "," in self.destination or ".." in self.destination:
            raise SandboxRejected("invalid_runtime_mount")
