"""Deterministic intersection; any denied axis dominates a pending approval."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from panestria.contracts.classification import resolve_classification
from panestria.contracts.policy import PolicyContext, PolicyRequest


@dataclass(frozen=True)
class PolicyDecision:
    outcome: Literal["PERMIT", "DENY", "APPROVAL_NEEDED"]
    reasons: tuple[str, ...]
    enforcement: tuple[str, ...]
    policy_version: int
    policy_sha256: str
    request_sha256: str


class PolicyEngine:
    def authorize(self, request: PolicyRequest, current_context: PolicyContext) -> PolicyDecision:
        context = current_context
        denied: list[str] = []
        approval: list[str] = []
        cloud = request.destination != "local"
        public_web = request.destination == "public-web"
        classification = resolve_classification(request.label)
        if (request.owner_id, request.project_id) != (context.owner_id, context.project_id):
            denied.append("scope_mismatch")
        if request.action not in context.trust.allowed_actions:
            denied.append("trust_action_denied")
        if context.trust.profile != "SYNTHETIC_DEV" and context.trust.runtime_certificate_sha256 is None:
            denied.append("runtime_uncertified")
        if cloud and context.trust.profile == "SYNTHETIC_DEV":
            denied.append("synthetic_cloud_denied")
        if classification.effective is None:
            denied.append("classification_unknown")
        if public_web and request.action != "external-send":
            denied.append("public_web_external_send_required")
        if cloud:
            if classification.effective in {"INTERNAL", "CONFIDENTIAL"}:
                denied.append("canonical_private_cloud_denied")
            if classification.effective == "RESTRICTED":
                denied.append(
                    "legacy_private_cloud_denied"
                    if classification.interpretation == "LEGACY_RESTRICTED"
                    else "restricted_cloud_denied"
                )
            if request.destination not in context.privacy.cloud_destinations:
                denied.append("destination_denied")
        mode = context.autonomy.actions[request.action]
        if mode in {"observe", "suggest"}:
            denied.append("autonomy_execution_denied")
        elif mode == "approve-first":
            approval.append("action_review")
        outcome: Literal["PERMIT", "DENY", "APPROVAL_NEEDED"]
        outcome = "DENY" if denied else "APPROVAL_NEEDED" if approval else "PERMIT"
        enforcement: tuple[str, ...]
        if public_web:
            enforcement = ("scoped-filesystem", "secret-free-tools", "public-fetch-broker", "outbound-disclosure")
        else:
            enforcement = (
                ("scoped-filesystem", "secret-free-tools", "provider-gateway")
                if cloud
                else ("scoped-filesystem", "secret-free-tools", "no-public-egress")
            )
        request_hash = hashlib.sha256(
            json.dumps(request.model_dump(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return PolicyDecision(
            outcome, tuple(sorted(denied or approval)), enforcement, context.version, context.sha256(), request_hash
        )
