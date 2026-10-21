"""Bounded profile owner API client: no retries, key access, inference or clear exports."""

import asyncio
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx2 as httpx
from pydantic import BaseModel, ConfigDict, Field

from panestria.cli.tui_client import LocalAskClient, TerminalUnavailable
from panestria.config_profile import load_profile_client
from panestria.contracts.profile import ProfileDocument, ProfileField
from panestria.contracts.style import StyleProfile


class ProfileReceipt(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)
    schema_version: int = Field(ge=1, le=1)
    profile_id: str
    revision_id: str
    revision: int = Field(ge=1, le=1024)
    row_version: int = Field(ge=0)
    key_id: str
    ciphertext_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    classification: str = Field(pattern="^RESTRICTED$")


@dataclass(frozen=True)
class StyleSource:
    profile_id: str
    key_id: str
    row_version: int | None
    receipt: ProfileReceipt | None = None
    document: ProfileDocument | None = field(default=None, repr=False)
    style: StyleProfile = field(default_factory=StyleProfile, repr=False)
    approved: bool = False


def style_document(source: StyleSource, style: StyleProfile, approved: bool) -> ProfileDocument:
    style = StyleProfile.model_validate(style)
    if type(approved) is not bool:
        raise ValueError("invalid_context_choice")
    # A correction is a complete encrypted snapshot. Preserve every other field,
    # approval and expiry; never silently replace a wider profile with style alone.
    old = source.document
    fields = {k: v.get_secret_value() for k, v in old.fields.items()} if old else {}
    fields["communication"] = style.model_dump_json()
    selected: list[ProfileField] = [v for v in old.approved_for_local_context if v != "communication"] if old else []
    if approved:
        selected.append("communication")
    return ProfileDocument.model_validate_json(
        json.dumps(
            {
                "fields": fields,
                "approved_for_local_context": selected,
                "valid_until": old.valid_until.isoformat() if old and old.valid_until else None,
            }
        )
    )


class ProfileClient(LocalAskClient):
    def __init__(self, config: Path):
        self.config, self._token = load_profile_client(config)

    async def _bounded(self, method: str, route: str, body: dict[str, Any] | None) -> dict[str, Any]:
        async with asyncio.timeout(5):
            async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=5) as client:
                async with client.stream(
                    method,
                    self.config.origin + route,
                    json=body,
                    headers={"Authorization": "Bearer " + self._token.get_secret_value()},
                ) as response:
                    if response.status_code in {401, 403}:
                        raise TerminalUnavailable("authentication_lost", clear=True)
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(data) + len(chunk) > 65536:
                            raise TerminalUnavailable("profile_response_size_limit", clear=True)
                        data.extend(chunk)
                    result = json.loads(data)
                    if not isinstance(result, dict):
                        raise TerminalUnavailable("profile_response_unconfirmed", clear=True)
                    if response.status_code not in {200, 201}:
                        code = result.get("code")
                        raise TerminalUnavailable(
                            code
                            if isinstance(code, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,79}", code)
                            else "profile_operation_unconfirmed",
                            clear=True,
                        )
                    return result

    def scope(self) -> None:
        self.activity()  # Typed canonical scope check, before any profile disclosure.

    def source(self, profile_id: str, expected_version: int) -> StyleSource:
        identity = str(UUID(profile_id))
        if type(expected_version) is not int or expected_version < 0:
            raise TerminalUnavailable("profile_version_invalid")
        self.scope()
        result = self._request(
            "POST",
            f"/v2/profiles/{identity}/view",
            {"schema_version": 1, "expected_version": expected_version, "purpose": "OWNER_REVIEW"},
        )
        try:
            document = ProfileDocument.model_validate_json(json.dumps(result.pop("document")))
            receipt = self._receipt_for(result, identity, expected_version)
            communication = document.fields.get("communication")
            style = (
                StyleProfile.model_validate_json(communication.get_secret_value()) if communication else StyleProfile()
            )
            return StyleSource(
                identity,
                receipt.key_id,
                expected_version,
                receipt,
                document,
                style,
                "communication" in document.approved_for_local_context,
            )
        except (KeyError, ValueError, TypeError):
            # An existing freeform statement must not be silently overwritten.
            raise TerminalUnavailable("structured_style_not_available", clear=True) from None

    def save(self, source: StyleSource, style: StyleProfile, approved: bool) -> ProfileReceipt:
        self.scope()
        document = style_document(source, style, approved)
        body: dict[str, Any] = {
            "schema_version": 1,
            "key_id": source.key_id,
            "intent": "SAVE_RESTRICTED_PROFILE",
            "document": {
                **document.model_dump(mode="json"),
                "fields": {k: v.get_secret_value() for k, v in document.fields.items()},
            },
        }
        if source.row_version is None:
            body["profile_id"] = str(UUID(source.profile_id))
            route, expected = "/v2/profiles", 0
        else:
            body["expected_version"] = source.row_version
            route, expected = f"/v2/profiles/{str(UUID(source.profile_id))}/correct", source.row_version + 1
        if len(json.dumps(body, ensure_ascii=False).encode()) > 32768:
            raise TerminalUnavailable("profile_request_size_limit")
        try:
            result = self._request("POST", route, body)
            receipt = self._receipt_for(result, source.profile_id, expected)
            if receipt.key_id != source.key_id or (source.receipt and receipt.revision != source.receipt.revision + 1):
                raise ValueError
            return receipt
        except (TerminalUnavailable, ValueError, TypeError) as error:
            if isinstance(error, TerminalUnavailable):
                error.uncertain = True
                raise
            raise TerminalUnavailable("profile_save_unconfirmed", clear=True, uncertain=True) from None

    @staticmethod
    def _receipt_for(result: dict[str, Any], profile_id: str, version: int) -> ProfileReceipt:
        receipt = ProfileReceipt.model_validate(result)
        if receipt.profile_id != profile_id or receipt.row_version != version:
            raise ValueError
        for value in (receipt.profile_id, receipt.key_id, receipt.revision_id):
            if str(UUID(value)) != value:
                raise ValueError
        return receipt
