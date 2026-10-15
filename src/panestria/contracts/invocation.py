"""Controller-created invocation bindings contain hashes and scope, never credentials."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from panestria.contracts.native_tools import ToolScope


class InvocationBinding(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    scope: ToolScope
    kind: Literal["native-proposal", "native-tool"]
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    def sha256(self) -> str:
        return hashlib.sha256(
            json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
