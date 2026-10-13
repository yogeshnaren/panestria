"""Independent axes, label lineage and client authority rejection."""

from __future__ import annotations

from itertools import product
from uuid import uuid4

import pytest
from pydantic import ValidationError

from panestria.contracts.policy import AutonomyAxis, PolicyContext, PolicyRequest, PrivacyAxis, TrustAxis
from panestria.policy.engine import PolicyEngine
from panestria.policy.labels import LabelService

ACTIONS = ["read", "edit", "tool-install", "external-send", "spend", "merge", "delete", "policy-change"]


def _context() -> PolicyContext:
    return PolicyContext(
        owner_id=str(uuid4()),
        project_id=str(uuid4()),
        version=1,
        trust=TrustAxis(
            version=1, profile="PERSONAL_SANDBOX", allowed_actions=ACTIONS, runtime_certificate_sha256="ab" * 32
        ),
        privacy=PrivacyAxis(version=1, cloud_destinations=["openai-api"], allow_private_cloud=True),
        autonomy=AutonomyAxis(version=1, actions={action: "act-and-report" for action in ACTIONS}),
    )


def _request(context: PolicyContext, **changes: object) -> PolicyRequest:
    body = dict(
        owner_id=context.owner_id,
        project_id=context.project_id,
        action="edit",
        label="PRIVATE",
        destination="local",
        effect_digest="cd" * 32,
    )
    body.update(changes)
    return PolicyRequest.model_validate(body)


def test_independent_axes_matrix(record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-007-TC01")
    record_property("source_clauses", "AOS-007-F01,AOS-007-F03,AOS-007-F04,AOS-007-AC01")
    context, engine = _context(), PolicyEngine()
    request = _request(context)
    # Each independent denial must survive all changes to the other two axes.
    for trust_allows, label, mode in product(
        [True, False],
        ["PUBLIC", "PRIVATE", "RESTRICTED", "UNKNOWN"],
        ["observe", "suggest", "approve-first", "act-and-report", "act-silently"],
    ):
        changed = context.model_copy(
            update={
                "trust": context.trust.model_copy(update={"allowed_actions": ACTIONS if trust_allows else []}),
                "autonomy": context.autonomy.model_copy(update={"actions": {action: mode for action in ACTIONS}}),
            }
        )
        outcome = engine.authorize(_request(context, label=label), changed).outcome
        if not trust_allows or label == "UNKNOWN" or mode in {"observe", "suggest"}:
            assert outcome == "DENY"
        elif mode == "approve-first":
            assert outcome == "APPROVAL_NEEDED"
        else:
            assert outcome == "PERMIT"
    restricted = _request(context, label="RESTRICTED", destination="openai-api")
    for profile in ["PERSONAL_SANDBOX", "TRUSTED_PROJECT", "HARDENED_WORKSPACE"]:
        raised = context.model_copy(update={"trust": context.trust.model_copy(update={"profile": profile})})
        assert engine.authorize(restricted, raised).outcome == "DENY"
        assert engine.authorize(request, raised).outcome == "PERMIT"
    observe = context.model_copy(update={"autonomy": AutonomyAxis(version=2, actions={a: "observe" for a in ACTIONS})})
    for label in ["PUBLIC", "PRIVATE", "RESTRICTED"]:
        assert engine.authorize(_request(context, label=label), observe).outcome == "DENY"
    before = context.sha256()
    for action in ACTIONS:
        selective = dict(context.autonomy.actions)
        selective[action] = "approve-first"
        changed = context.model_copy(update={"autonomy": AutonomyAxis(version=2, actions=selective)})
        for other in ACTIONS:
            assert engine.authorize(_request(context, action=other), changed).outcome == (
                "APPROVAL_NEEDED" if other == action else "PERMIT"
            )
    assert context.sha256() == before


def test_restricted_cloud_and_labels(record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-007-TC02")
    record_property("source_clauses", "AOS-007-F02,AOS-007-AC02,AOS-007-AC03")
    context, engine, labels = _context(), PolicyEngine(), LabelService()
    for label in ["RESTRICTED", "UNKNOWN"]:
        decision = engine.authorize(_request(context, label=label, destination="openai-api"), context)
        assert decision.outcome == "DENY"
    assert labels.derive(["PUBLIC", "PRIVATE"]) == "PRIVATE"
    assert labels.derive(["PUBLIC", "PRIVATE", "RESTRICTED"]) == "RESTRICTED"
    assert labels.derive([]) == labels.derive([None]) == labels.derive(["RESTRICTED", "UNKNOWN"]) == "UNKNOWN"
    for derived_kind in ["snippet", "embedding", "prompt", "artifact", "trace"]:
        lineage = {derived_kind: labels.derive(["PUBLIC", "RESTRICTED"])}
        assert lineage[derived_kind] == "RESTRICTED"
    private_cloud = engine.authorize(_request(context, destination="openai-api"), context)
    assert private_cloud.outcome == "APPROVAL_NEEDED" and "private_cloud_review" in private_cloud.reasons
    assert engine.authorize(_request(context, destination="unconfigured-provider"), context).outcome == "DENY"


def test_model_cannot_self_promote(record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-007-TC04")
    record_property("source_clauses", "AOS-007-F01,AOS-007-F04")
    context = _context()
    for authority in ["approved", "approval_granted", "policy_granted", "owner_approved", "action_permit"]:
        with pytest.raises(ValidationError):
            PolicyRequest.model_validate({**_request(context).model_dump(), authority: True})
    missing = context.model_copy(
        update={"trust": context.trust.model_copy(update={"runtime_certificate_sha256": None})}
    )
    assert PolicyEngine().authorize(_request(context), missing).outcome == "DENY"
    other = _request(context, project_id=str(uuid4()))
    assert PolicyEngine().authorize(other, context).reasons == ("scope_mismatch",)
    with pytest.raises(ValidationError):
        AutonomyAxis(version=1, actions={"edit": "act-silently"})
