"""Exact scoped declaration review; no credential, root, provider or runtime calls."""

import json
from pathlib import Path
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, TypeAdapter

from panestria.cli.profile_client import ProfileClient
from panestria.cli.tui_client import TerminalUnavailable
from panestria.contracts.connections import (
    ConnectionDecisionView,
    ConnectionGrantView,
    ConnectionId,
    ConnectionReviewView,
    ConnectionScopeView,
    DecideReview,
    SubmitReview,
)

M = TypeVar("M", bound=BaseModel)
_ID = TypeAdapter(ConnectionId)


class ConnectionClient:
    def __init__(self, config: Path):
        self.http = ProfileClient(config)  # Private loopback owner settings only; no profile/key access.

    def _view(self, model: type[M], method: str, route: str, body: dict[str, Any] | None = None) -> M:
        self.http.scope()  # Typed canonical owner/project check before any disclosure.
        try:
            return model.model_validate_json(json.dumps(self.http._request(method, route, body)))
        except (TypeError, ValueError):
            raise TerminalUnavailable("connection_response_unconfirmed", clear=True) from None

    def _scope(self, view: ConnectionReviewView | ConnectionGrantView) -> None:
        if (view.manifest.owner_id, view.manifest.project_id) != (
            str(self.http.config.owner_id),
            str(self.http.config.project_id),
        ):
            raise TerminalUnavailable("server_scope_mismatch", clear=True)

    def scope(self) -> ConnectionScopeView:
        view = self._view(ConnectionScopeView, "GET", "/v2/connections/scope")
        if (view.owner_id, view.project_id) != (str(self.http.config.owner_id), str(self.http.config.project_id)):
            raise TerminalUnavailable("server_scope_mismatch", clear=True)
        return view

    def preview(self, proposal_id: str) -> ConnectionReviewView:
        identity = _ID.validate_python(proposal_id)
        view = self._view(ConnectionReviewView, "GET", f"/v2/connections/reviews/{identity}")
        self._scope(view)
        if view.proposal_id != identity:
            raise TerminalUnavailable("connection_response_unconfirmed", clear=True)
        return view

    def current(self, grant_id: str) -> ConnectionGrantView:
        identity = _ID.validate_python(grant_id)
        view = self._view(ConnectionGrantView, "GET", f"/v2/connections/grants/{identity}")
        self._scope(view)
        if view.grant_id != identity:
            raise TerminalUnavailable("connection_response_unconfirmed", clear=True)
        return view

    def propose(self, request: SubmitReview) -> ConnectionReviewView:
        manifest = request.change.manifest
        if manifest is not None and (manifest.owner_id, manifest.project_id) != (
            str(self.http.config.owner_id),
            str(self.http.config.project_id),
        ):
            raise TerminalUnavailable("connection_scope_mismatch", clear=True)
        view = self._view(ConnectionReviewView, "POST", "/v2/connections/reviews", request.model_dump(mode="json"))
        self._scope(view)
        change = request.change
        if (view.proposal_id, view.expected_version, view.operation, view.policy_ref) != (
            change.proposal_id,
            change.expected_version,
            change.operation,
            change.policy_ref,
        ) or (change.grant_id is not None and view.grant_id != change.grant_id):
            raise TerminalUnavailable("connection_response_unconfirmed", clear=True)
        if manifest is not None and view.manifest != manifest:
            raise TerminalUnavailable("connection_response_unconfirmed", clear=True)
        return view

    def decide(self, source: ConnectionReviewView, choice: Literal["approve", "deny"]) -> ConnectionDecisionView:
        # Fresh preview fences a changed/expired/already-decided source. A lost
        # POST is never repeated by this client or the terminal.
        current = self.preview(source.proposal_id)
        if current.state != "PENDING" or current.model_copy(update={"replayed": source.replayed}) != source:
            raise TerminalUnavailable("connection_review_changed_reopen", clear=True)
        if self.scope().policy_ref != source.policy_ref:
            raise TerminalUnavailable("connection_policy_changed_reopen", clear=True)
        decision = DecideReview(schema_version=1, effect_digest=source.effect_digest, decision=choice)
        result = self._view(
            ConnectionDecisionView,
            "POST",
            f"/v2/connections/reviews/{source.proposal_id}/decision",
            decision.model_dump(mode="json"),
        )
        if (result.proposal_id, result.grant_id, result.effect_digest, result.decision) != (
            source.proposal_id,
            source.grant_id,
            source.effect_digest,
            "APPROVED" if choice == "approve" else "DENIED",
        ) or (result.decision == "APPROVED" and result.granted_version != source.expected_version + 1):
            raise TerminalUnavailable("connection_decision_unconfirmed", clear=True)
        return result
