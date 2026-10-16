"""Closed declaration scopes, not connector enforcement or live permissions."""

import json
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from connection_support import manifest, proposal
from panestria.contracts.connections import ConnectionBudget, ConnectionManifest

OWNER = "22222222-2222-2222-2222-222222222222"
PROJECT = "33333333-3333-3333-3333-333333333333"
POLICY = "project-policy:1:" + "ab" * 32


def test_canonical_frozen_roundtrip_and_independent_actions():
    first = manifest(
        OWNER,
        PROJECT,
        actions=("send", "read"),
        data_classes=("RESTRICTED", "PUBLIC"),
        origins=("https://other.example.com", "https://example.com"),
    )
    body = first.model_dump(mode="json")
    body["actions"].reverse()
    body["data_classes"].reverse()
    body["origins"].reverse()
    second = ConnectionManifest.model_validate_json(json.dumps(body))
    assert first.sha256() == second.sha256()
    assert first.actions == ("read", "send") and "write" not in first.actions and "spend" not in first.actions
    with pytest.raises(ValidationError):
        first.actions = ("spend",)
    utc = first.expires_at
    shifted = first.model_copy(update={"expires_at": utc.astimezone(timezone(timedelta(hours=5)))})
    assert ConnectionManifest.model_validate(shifted).sha256() == first.sha256()


@pytest.mark.parametrize(
    "field,value",
    [
        ("approved", True),
        ("credential", "SYNTHETIC"),
        ("secret_handle", "SYNTHETIC"),
        ("root_paths", ["/home/example"]),
        ("account_ref", "owner@example.com"),
        ("schema_version", True),
        ("schema_version", 2),
        ("actions", ["execute"]),
        ("actions", ["read", "read"]),
        ("data_classes", ["PRIVATE"]),
        ("data_classes", ["UNKNOWN"]),
        ("data_classes", ["PUBLIC", "PUBLIC"]),
        ("configuration_sha256", "not-a-pin"),
        ("conformance_sha256", "PASS"),
        ("expires_at", "2026-10-16T12:00:00"),
        ("root_refs", ["/tmp/example"]),
    ],
)
def test_worker_authority_credentials_unknown_scope_and_coercions_rejected(field, value):
    body = manifest(OWNER, PROJECT).model_dump(mode="json")
    body[field] = value
    with pytest.raises(ValidationError):
        ConnectionManifest.model_validate_json(json.dumps(body))


@pytest.mark.parametrize(
    "origin",
    [
        "http://example.com",
        "https://example.com/",
        "https://example.com:443",
        "https://EXAMPLE.com",
        "https://user:password@example.com",
        "https://example.com?q=secret",
        "https://example.com#part",
        "https://*.example.com",
        "https://127.0.0.1",
        "https://[::1]",
        "https://localhost",
        "https://example.com\\@evil.test",
        "https://exa mple.com",
        "https://éxample.com",
    ],
)
def test_origins_are_exact_bounded_canonical_names_not_urls_or_wildcards(origin):
    with pytest.raises(ValidationError):
        manifest(OWNER, PROJECT, origins=(origin,))


@pytest.mark.parametrize(
    "changes",
    [
        {"actions": ("write",), "origins": ()},
        {"actions": ("delete",), "origins": ()},
        {"actions": ("send",), "origins": ()},
        {"actions": ("spend",)},
        {"actions": ("read",), "origins": ()},
    ],
)
def test_each_declared_action_requires_its_own_bound_scope(changes):
    with pytest.raises(ValidationError):
        manifest(OWNER, PROJECT, **changes)


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_calls", False),
        ("max_bytes", 0),
        ("max_cash_microusd", -1),
        ("max_cash_microusd", 1.0),
        ("max_wall_seconds", 3601),
    ],
)
def test_budget_is_closed_bounded_and_not_a_float_or_boolean(field, value):
    body = dict(max_calls=1, max_bytes=1, max_wall_seconds=1, max_cash_microusd=0)
    body[field] = value
    with pytest.raises(ValidationError):
        ConnectionBudget.model_validate(body)


@pytest.mark.parametrize(
    "changes",
    [
        {"operation": "REVOKE"},
        {"expected_version": 1},
        {"expected_version": True},
        {"policy_ref": "local"},
        {"operation": "REVOKE", "grant_id": OWNER, "expected_version": 1},
        {"operation": "REPLACE", "grant_id": OWNER, "expected_version": 1_000_000},
    ],
)
def test_review_does_not_invent_initial_revoke_or_unversioned_policy(changes):
    with pytest.raises(ValidationError):
        proposal(POLICY, manifest(OWNER, PROJECT), **changes)


def test_explicit_root_and_cash_declarations_still_do_not_imply_other_actions():
    value = manifest(
        OWNER,
        PROJECT,
        actions=("write", "spend"),
        root_refs=("cd" * 32,),
        budget=ConnectionBudget(max_calls=1, max_bytes=1, max_cash_microusd=1, max_wall_seconds=1),
    )
    assert value.actions == ("spend", "write") and "send" not in value.actions
    assert value.expires_at > datetime.now(UTC)


@pytest.mark.parametrize("action", ["write", "delete"])
def test_scoped_remote_action_does_not_invent_local_roots_or_send_permission(action):
    value = manifest(OWNER, PROJECT, actions=(action,))
    assert value.origins == ("https://example.com",) and not value.root_refs
    assert value.actions == (action,) and "send" not in value.actions
