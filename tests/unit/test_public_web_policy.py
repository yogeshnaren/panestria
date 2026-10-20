"""Pure policy intersections; injected references do not certify a runtime or send."""

import hashlib
import json
from itertools import product

import pytest
from pydantic import ValidationError

from panestria.contracts.policy import AutonomyAxis, PolicyContext, PolicyRequest, PrivacyAxis, TrustAxis
from panestria.policy.engine import PolicyEngine

ACTIONS = ["read", "edit", "tool-install", "external-send", "spend", "merge", "delete", "policy-change"]


def test_decision_seals_effect_and_policy_and_prescribes_each_transport():
    body = context().model_dump()
    body["privacy"]["cloud_destinations"] = ["public-web", "claude-subscription"]
    body["autonomy"]["actions"]["external-send"] = "act-and-report"
    policy = PolicyContext.model_validate(body)
    expected = {
        "local": ("scoped-filesystem", "secret-free-tools", "no-public-egress"),
        "claude-subscription": ("scoped-filesystem", "secret-free-tools", "provider-gateway"),
        "public-web": ("scoped-filesystem", "secret-free-tools", "public-fetch-broker", "outbound-disclosure"),
    }
    for destination, enforcement in expected.items():
        original = request(policy, destination=destination)
        decision = PolicyEngine().authorize(original, policy)
        assert decision.outcome == "PERMIT" and decision.enforcement == enforcement
        assert decision.policy_version == 7 and decision.policy_sha256 == policy.sha256()
        canonical = json.dumps(original.model_dump(), sort_keys=True, separators=(",", ":")).encode()
        assert decision.request_sha256 == hashlib.sha256(canonical).hexdigest()
        changed = request(policy, destination=destination, effect_digest="ef" * 32)
        assert PolicyEngine().authorize(changed, policy).request_sha256 != decision.request_sha256


def context():
    return PolicyContext(
        owner_id="11111111-1111-1111-1111-111111111111",
        project_id="22222222-2222-2222-2222-222222222222",
        version=7,
        trust=TrustAxis(
            version=3,
            profile="PERSONAL_SANDBOX",
            allowed_actions=["read", "external-send"],
            runtime_certificate_sha256="ab" * 32,
        ),
        privacy=PrivacyAxis(version=4, cloud_destinations=["claude-subscription", "anthropic-api"]),
        autonomy=AutonomyAxis(version=2, actions={a: "approve-first" for a in ACTIONS}),
    )


def request(policy, **changes):
    return PolicyRequest.model_validate(
        {
            "owner_id": policy.owner_id,
            "project_id": policy.project_id,
            "action": "external-send",
            "label": "PUBLIC",
            "destination": "public-web",
            "effect_digest": "cd" * 32,
            **changes,
        }
    )


def test_existing_policy_fingerprint_is_byte_compatible_with_prechange_main():
    # Recorded on clean main41458fe before changing the destination schema.
    policy = context()
    assert policy.sha256() == "fd00816f0a18bdda6726bfbbd9a8ea0014aed99b4373e1904b72adb014948540"
    assert PolicyContext.model_validate_json(policy.model_dump_json()).sha256() == policy.sha256()
    assert PrivacyAxis(version=1).cloud_destinations == []
    assert PolicyEngine().authorize(request(policy), policy).outcome == "DENY"


@pytest.mark.parametrize("label", ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED", "PRIVATE", "UNKNOWN"])
@pytest.mark.parametrize("mode", ["observe", "suggest", "approve-first", "act-and-report", "act-silently"])
def test_web_requires_each_axis_and_never_sends_private_or_unknown_labels(label, mode):
    original = context()
    for trust_allows, web_enabled in product([True, False], repeat=2):
        body = original.model_dump()
        body["trust"]["allowed_actions"] = ["external-send"] if trust_allows else []
        body["privacy"] = {
            "version": 4,
            "cloud_destinations": ["public-web"] if web_enabled else [],
            "allow_private_cloud": True,  # Legacy flag cannot widen canonical private access.
        }
        body["autonomy"]["actions"]["external-send"] = mode
        policy = PolicyContext.model_validate(body)
        decision = PolicyEngine().authorize(request(policy, label=label), policy)
        if label != "PUBLIC" or not trust_allows or not web_enabled or mode in {"observe", "suggest"}:
            assert decision.outcome == "DENY"
        elif mode == "approve-first":
            assert decision.outcome == "APPROVAL_NEEDED" and decision.reasons == ("action_review",)
        else:
            assert decision.outcome == "PERMIT"
        assert "public-fetch-broker" in decision.enforcement and "outbound-disclosure" in decision.enforcement
        assert "provider-gateway" not in decision.enforcement and "no-public-egress" not in decision.enforcement
    assert original.sha256() == context().sha256()


@pytest.mark.parametrize("action", [a for a in ACTIONS if a != "external-send"])
def test_web_cannot_hide_an_outbound_effect_as_a_read_or_other_action(action):
    body = context().model_dump()
    body["privacy"]["cloud_destinations"] = ["public-web"]
    body["trust"]["allowed_actions"] = ACTIONS
    body["autonomy"]["actions"] = {a: "act-and-report" for a in ACTIONS}
    policy = PolicyContext.model_validate(body)
    decision = PolicyEngine().authorize(request(policy, action=action), policy)
    assert decision.outcome == "DENY" and "public_web_external_send_required" in decision.reasons


def test_model_provider_grants_and_web_grant_do_not_imply_each_other():
    body = context().model_dump()
    body["autonomy"]["actions"]["external-send"] = "act-and-report"
    body["privacy"]["cloud_destinations"] = ["public-web"]
    policy = PolicyContext.model_validate(body)
    assert PolicyEngine().authorize(request(policy), policy).outcome == "PERMIT"
    for destination in ["claude-subscription", "anthropic-api", "openai-api"]:
        assert PolicyEngine().authorize(request(policy, destination=destination), policy).outcome == "DENY"
        body["privacy"]["cloud_destinations"] = [destination]
        provider = PolicyContext.model_validate(body)
        assert PolicyEngine().authorize(request(provider), provider).outcome == "DENY"


def test_scope_synthetic_and_missing_certificate_denials_survive_all_other_permissions():
    body = context().model_dump()
    body["privacy"]["cloud_destinations"] = ["public-web"]
    body["autonomy"]["actions"]["external-send"] = "act-silently"
    policy = PolicyContext.model_validate(body)
    for key in ["owner_id", "project_id"]:
        decision = PolicyEngine().authorize(request(policy, **{key: "33" * 18}), policy)
        assert decision.outcome == "DENY" and "scope_mismatch" in decision.reasons
    for profile, certificate, reason in [
        ("SYNTHETIC_DEV", None, "synthetic_cloud_denied"),
        ("PERSONAL_SANDBOX", None, "runtime_uncertified"),
    ]:
        body["trust"].update(profile=profile, runtime_certificate_sha256=certificate)
        changed = PolicyContext.model_validate(body)
        result = PolicyEngine().authorize(request(changed), changed)
        assert result.outcome == "DENY" and reason in result.reasons


@pytest.mark.parametrize("destination", ["PUBLIC-WEB", "public-web/", "https://example.com", "local", 3, None])
def test_destination_grants_are_closed_and_never_raw_host_names(destination):
    with pytest.raises(ValidationError):
        PrivacyAxis(version=1, cloud_destinations=[destination])
