"""Cacheless approved-field overlay; never write plaintext into context packs."""

from __future__ import annotations

import hmac
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError

from panestria.contracts.policy import PolicyRequest
from panestria.contracts.profile_context import ProfileSelectionRequest
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.repositories.policy import active_policy_ref, current_policy, require_current_policy
from panestria.kernel.uow import UnitOfWork
from panestria.memory.vault import ProfileRef, ProfileVault
from panestria.policy.engine import PolicyEngine


class ProfileSelection(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    owner_id: str
    project_id: str
    request: ProfileSelectionRequest
    source: ProfileRef
    policy_ref: str
    content: SecretStr
    label: Literal["RESTRICTED"] = "RESTRICTED"
    offline: Literal[True] = True


class ProfileContext:
    def __init__(self, vault: ProfileVault) -> None:
        self.vault = vault

    def select(self, uow: UnitOfWork, actor: Actor, request: ProfileSelectionRequest) -> ProfileSelection:
        self.vault._enabled()
        try:
            request = ProfileSelectionRequest.model_validate(request.model_dump())
        except ValidationError:
            raise KernelDenied("invalid_profile_selection") from None
        policy_ref = active_policy_ref(uow, actor.owner_id, actor.project_id)
        if policy_ref is None:
            raise KernelDenied("policy_unconfigured")
        require_current_policy(uow, actor, policy_ref)
        decision = PolicyEngine().authorize(
            PolicyRequest(
                owner_id=actor.owner_id,
                project_id=actor.project_id,
                action="read",
                label="RESTRICTED",
                destination="local",
                effect_digest=request.sha256(),
            ),
            current_policy(uow, actor),
        )
        if decision.outcome != "PERMIT":
            raise KernelDenied("profile_policy_denied")
        ref, document = self.vault.read(uow, actor, request.profile_id)
        if ref.row_version != request.expected_row_version:
            raise KernelDenied("version_conflict")
        if not set(request.fields).issubset(document.approved_for_local_context):
            raise KernelDenied("profile_fields_not_approved")
        content = json.dumps(
            {
                "schema_version": 1,
                "classification": "RESTRICTED",
                "provenance": "owner_statement",
                "purpose": request.purpose,
                "fields": {name: document.fields[name].get_secret_value() for name in request.fields},
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if len(content.encode()) > request.max_bytes:
            raise KernelDenied("profile_context_size_limit")
        return ProfileSelection(
            owner_id=actor.owner_id,
            project_id=actor.project_id,
            request=request,
            source=ref,
            policy_ref=policy_ref,
            content=SecretStr(content),
        )

    def revalidate(self, uow: UnitOfWork, actor: Actor, selection: ProfileSelection) -> ProfileSelection:
        if (selection.owner_id, selection.project_id) != (actor.owner_id, actor.project_id):
            raise KernelDenied("not_found")
        latest = self.select(uow, actor, selection.request)
        # Reconstruct rather than trusting client-supplied text or a plaintext hash.
        if (selection.source, selection.policy_ref, selection.label, selection.offline) != (
            latest.source,
            latest.policy_ref,
            "RESTRICTED",
            True,
        ) or not hmac.compare_digest(
            selection.content.get_secret_value().encode(), latest.content.get_secret_value().encode()
        ):
            raise KernelDenied("profile_context_stale")
        return latest
