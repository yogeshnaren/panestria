"""Conservative compatibility must precede sensitive profile/schema rollout."""

from __future__ import annotations

from itertools import permutations, product
from typing import get_args
from uuid import uuid4

import pytest

from panestria.contracts.classification import CanonicalClass, derive_classification, resolve_classification
from panestria.contracts.goal import GoalContract
from panestria.contracts.policy import AutonomyAxis, PolicyContext, PolicyRequest, PrivacyAxis, TrustAxis
from panestria.policy.engine import PolicyEngine

ACTIONS = ["read", "edit", "tool-install", "external-send", "spend", "merge", "delete", "policy-change"]


def test_goal_wire_classification_does_not_change() -> None:
    expected = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]
    assert list(get_args(CanonicalClass)) == expected
    assert GoalContract.model_json_schema()["properties"]["privacy_class"]["enum"] == expected


@pytest.mark.parametrize("value", [None, "UNKNOWN", "private", "", " SECRET ", [], {}, 0, False])
def test_unknown_is_never_an_authorized_class(value: object) -> None:
    result = resolve_classification(value)
    assert result.effective is None and result.interpretation == "UNKNOWN"
    assert derive_classification(["RESTRICTED", value]).effective is None


def test_strictest_source_and_legacy_provenance_survive_ordering() -> None:
    for ordering in permutations(["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]):
        assert derive_classification(ordering).effective == "RESTRICTED"
    assert derive_classification(["PUBLIC", "INTERNAL"]).effective == "INTERNAL"
    assert derive_classification(["INTERNAL", "CONFIDENTIAL"]).effective == "CONFIDENTIAL"
    assert derive_classification([]).effective is None
    for ordering in permutations(["PUBLIC", "PRIVATE", "CONFIDENTIAL"]):
        result = derive_classification(ordering)
        assert result.effective == "RESTRICTED" and result.interpretation == "LEGACY_RESTRICTED"
    assert resolve_classification("PRIVATE").effective == "RESTRICTED"
    assert resolve_classification("RESTRICTED").interpretation == "CANONICAL"


def context(*, allow_private: bool) -> PolicyContext:
    return PolicyContext(
        owner_id=str(uuid4()),
        project_id=str(uuid4()),
        version=1,
        trust=TrustAxis(
            version=1, profile="PERSONAL_SANDBOX", allowed_actions=ACTIONS, runtime_certificate_sha256="ab" * 32
        ),
        privacy=PrivacyAxis(
            version=1,
            cloud_destinations=["claude-subscription", "anthropic-api", "openai-api"],
            allow_private_cloud=allow_private,
        ),
        autonomy=AutonomyAxis(version=1, actions={action: "act-silently" for action in ACTIONS}),
    )


def test_legacy_cloud_denial_dominates_old_flags_actions_and_destinations() -> None:
    engine = PolicyEngine()
    for allow, action, destination in product(
        [False, True],
        ACTIONS,
        ["claude-subscription", "anthropic-api", "openai-api", "other"],
    ):
        policy = context(allow_private=allow)
        before = policy.model_dump()
        request = PolicyRequest(
            owner_id=policy.owner_id,
            project_id=policy.project_id,
            action=action,
            label="PRIVATE",
            destination=destination,
            effect_digest="cd" * 32,
        )
        decision = engine.authorize(request, policy)
        assert decision.outcome == "DENY" and "legacy_private_cloud_denied" in decision.reasons
        # The interpretation does not rewrite wire/audit inputs or policy history.
        assert request.model_dump()["label"] == "PRIVATE"
        assert policy.model_dump() == before and decision.policy_sha256 == policy.sha256()
        assert engine.authorize(request.model_copy(update={"destination": "local"}), policy).outcome == "PERMIT"
        assert (
            engine.authorize(request.model_copy(update={"label": "UNKNOWN", "destination": "local"}), policy).outcome
            == "DENY"
        )


def test_legacy_flag_does_not_widen_public_or_restricted_requests() -> None:
    policy = context(allow_private=True)
    for label, destination, expected in [
        ("PUBLIC", "local", "PERMIT"),
        ("PUBLIC", "claude-subscription", "PERMIT"),
        ("RESTRICTED", "local", "PERMIT"),
        ("RESTRICTED", "claude-subscription", "DENY"),
    ]:
        request = PolicyRequest.model_validate(
            dict(
                owner_id=policy.owner_id,
                project_id=policy.project_id,
                action="read",
                label=label,
                destination=destination,
                effect_digest="cd" * 32,
            )
        )
        assert PolicyEngine().authorize(request, policy).outcome == expected
