"""Explicit pinned profile selection for the existing restricted offline Ask terminal."""

import re
import resource
from pathlib import Path
from typing import Any
from uuid import UUID

from panestria.cli.profile_client import ProfileClient
from panestria.cli.tui import run_terminal
from panestria.cli.tui_client import LocalAskClient, TerminalUnavailable
from panestria.config_local import read_private
from panestria.contracts.ask import ProfileAskSubmission
from panestria.contracts.profile_context import ProfileSelectionRequest


class ProfileAskClient(ProfileClient):
    view_title = "Panestria | PROFILE ASK | restricted offline terminal"

    def __init__(self, config: Path, selection: Path):
        super().__init__(config)
        self.selection = ProfileSelectionRequest.model_validate_json(read_private(selection, 4096))

    @property
    def selection_notice(self) -> str:
        return (
            f"Profile {self.selection.profile_id} row {self.selection.expected_row_version}; {self.selection.purpose}"
        )

    def request_seconds(self, route: str) -> float:
        return 65.0 if route == "/v2/ask" else 5.0

    @staticmethod
    def keep_request(error: TerminalUnavailable) -> None:
        error.clear = error.code in {
            "authentication_lost",
            "server_scope_mismatch",
            "profile_scope_unconfirmed",
            "profile_disabled",
            "profile_not_configured",
        }

    def status(self) -> dict[str, Any]:
        try:
            self.scope()
            result = self._request("GET", "/v2/ask/status")
        except TerminalUnavailable as error:
            self.keep_request(error)
            raise
        if (
            result.get("schema_version") != 2
            or result.get("owner_id") != str(self.config.owner_id)
            or result.get("project_id") != str(self.config.project_id)
            or result.get("profiles") != "EXPLICITLY_ENABLED"
            or result.get("privacy_label") != "RESTRICTED"
            or result.get("offline") is not True
            or result.get("cloud_fallback") != "NONE"
            or result.get("readiness") != "KEY_MODEL_CHECKED_PER_REQUEST"
        ):
            raise TerminalUnavailable("profile_scope_unconfirmed", clear=True)
        return result

    def ask(self, request_id: str, question: str) -> dict[str, Any]:
        request = ProfileAskSubmission(
            schema_version=2,
            request_id=request_id,
            project_id=str(self.config.project_id),
            question=question,
            privacy_label="RESTRICTED",
            offline=True,
            retain_response=False,
            context_tokens=4096,
            profile=self.selection,
        )
        self.status()  # No question disclosed until fixed scope/profile mode is confirmed.
        try:
            result = self._request("POST", "/v2/ask", request.model_dump(mode="json"))
            if result.get("schema_version") != 2:
                raise TerminalUnavailable("profile_receipt_unconfirmed")
            return self.profile_receipt(result, request_id)
        except TerminalUnavailable as error:
            error.uncertain = True
            # Keep a known request ID on an ordinary error reply. A POST may
            # already be durable; only auth/scope loss clears sensitive views.
            self.keep_request(error)
            raise

    def receipt(self, request_id: str) -> dict[str, Any]:
        identity = str(UUID(request_id))
        try:
            return self.profile_receipt(self._request("GET", "/v1/ask/" + identity), identity)
        except TerminalUnavailable as error:
            self.keep_request(error)
            error.uncertain = True
            raise

    def profile_receipt(self, result: dict[str, Any], request_id: str) -> dict[str, Any]:
        result = LocalAskClient._receipt(result, request_id)
        selected = result.get("profile_context")
        if (
            result.get("privacy_label") != "RESTRICTED"
            or result.get("response_digest_mode") != "OMITTED_RESTRICTED_PROFILE"
            or "response_sha256" not in result
            or result["response_sha256"] is not None
            or not isinstance(selected, dict)
            or selected.get("profile_id") != self.selection.profile_id
            or type(selected.get("row_version")) is not int
            or selected.get("row_version") != self.selection.expected_row_version
            or selected.get("selected_fields") != list(self.selection.fields)
            or selected.get("purpose") != self.selection.purpose
        ):
            raise TerminalUnavailable("profile_receipt_unconfirmed", clear=True)
        try:
            if str(UUID(selected["revision_id"])) != selected["revision_id"]:
                raise ValueError
            if type(selected["revision"]) is not int or selected["revision"] < 1:
                raise ValueError
            for name in ("ciphertext_sha256", "manifest_sha256"):
                if re.fullmatch(r"[0-9a-f]{64}", selected[name]) is None:
                    raise ValueError
        except (ValueError, TypeError, KeyError):
            raise TerminalUnavailable("profile_receipt_unconfirmed", clear=True) from None
        return result


def profile_ask_terminal(config: Path, selection: Path, restricted_offline: bool) -> None:
    if not restricted_offline:
        raise TerminalUnavailable("explicit_restricted_profile_ask_required")
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    run_terminal(lambda: ProfileAskClient(config, selection))
