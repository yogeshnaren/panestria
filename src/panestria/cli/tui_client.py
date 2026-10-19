"""Bounded owner client for the existing scoped offline Ask HTTP application."""

import asyncio
import json
import re
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx2 as httpx

from panestria.config_local import load_local_settings
from panestria.contracts.ask import AskSubmission

CONTROL_SECONDS = 5.0
ASK_SECONDS = 65.0


class TerminalUnavailable(Exception):
    def __init__(self, code: str, *, clear: bool = False, uncertain: bool = False):
        self.code, self.clear, self.uncertain = code, clear, uncertain
        super().__init__(code)


class LocalAskClient:
    def __init__(self, config: Path):
        self.config, self._token = load_local_settings(config)

    def _request(self, method: str, route: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            return asyncio.run(self._bounded(method, route, body))
        except (TimeoutError, httpx.HTTPError, OSError, ValueError):
            # A failed POST can already exist durably. Never replay it here.
            raise TerminalUnavailable("connection_unconfirmed_check_receipt") from None

    async def _bounded(self, method: str, route: str, body: dict[str, Any] | None) -> dict[str, Any]:
        async with asyncio.timeout(ASK_SECONDS if route == "/v1/ask" else CONTROL_SECONDS):
            async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=ASK_SECONDS) as c:
                async with c.stream(
                    method,
                    self.config.origin + route,
                    json=body,
                    headers={"Authorization": "Bearer " + self._token.get_secret_value()},
                ) as response:
                    if response.status_code in {401, 403}:
                        raise TerminalUnavailable("authentication_lost", clear=True)
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(data) + len(chunk) > 1024 * 1024:
                            raise TerminalUnavailable("response_size_limit")
                        data.extend(chunk)
                    result = json.loads(data)
                    if not isinstance(result, dict):
                        raise TerminalUnavailable("invalid_response")
                    if response.status_code != 200:
                        code = result.get("code")
                        raise TerminalUnavailable(
                            code
                            if isinstance(code, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,79}", code)
                            else "request_unavailable"
                        )
                    return result

    def status(self) -> dict[str, Any]:
        result = self._request("GET", "/v1/local/status")
        if (
            result.get("owner_id") != str(self.config.owner_id)
            or result.get("project_id") != str(self.config.project_id)
            or result.get("cloud_routes") != "UNMOUNTED"
            or result.get("profiles") != "DISABLED"
        ):
            raise TerminalUnavailable("server_scope_mismatch", clear=True)
        if result.get("model_socket_present") is not True:
            raise TerminalUnavailable("model_not_ready")
        return result

    def ask(self, request_id: str, question: str) -> dict[str, Any]:
        submission = AskSubmission(
            request_id=request_id,
            project_id=str(self.config.project_id),
            question=question,
            privacy_label="RESTRICTED",
            offline=True,
            retain_response=False,
        )
        self.status()  # Same selected scope must be available before disclosure.
        try:
            result = self._request("POST", "/v1/ask", submission.model_dump())
            return self._receipt(result, request_id)
        except TerminalUnavailable as error:
            error.uncertain = True  # Inspect durable receipt; never assume that a POST did not commit.
            raise

    def receipt(self, request_id: str) -> dict[str, Any]:
        identity = str(UUID(request_id))
        return self._receipt(self._request("GET", "/v1/ask/" + identity), identity)

    def cancel(self, request_id: str) -> dict[str, Any]:
        identity = str(UUID(request_id))
        result = self._request("POST", "/v1/ask/" + identity + "/cancel", {})
        if result.get("request_id") != identity or result.get("state") not in {"CANCELLED", "COMPLETED", "FAILED"}:
            raise TerminalUnavailable("cancellation_unconfirmed_check_receipt")
        return result

    @staticmethod
    def _receipt(result: dict[str, Any], request_id: str) -> dict[str, Any]:
        if (
            result.get("request_id") != request_id
            or result.get("state") not in {"PREPARED", "RUNNING", "COMPLETED", "CANCELLED", "FAILED"}
            or result.get("offline") is not True
            or result.get("response_retained") is not False
            or ("text" in result and not isinstance(result["text"], str))
        ):
            raise TerminalUnavailable("receipt_unconfirmed")
        return result
