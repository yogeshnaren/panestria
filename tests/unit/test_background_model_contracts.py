"""Immutable requested-model scope preserves legacy bytes and independent windows."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from panestria.contracts.background import BackgroundWorkPolicy
from panestria.contracts.background_run import BackgroundRun


def legacy():
    account = str(uuid4())
    return {
        "policy_id": str(uuid4()),
        "owner_id": str(uuid4()),
        "project_id": str(uuid4()),
        "quota_windows": [{"provider": "claude-subscription", "account_ref": account, "window_ref": "weekly"}],
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    }


def test_legacy_null_policy_and_absent_run_model_remain_hash_compatible():
    policy = BackgroundWorkPolicy.model_validate_json(json.dumps(legacy()))
    body = policy.model_dump(mode="json")
    assert body["schema_version"] == 1 and body["model_ref"] is None
    assert BackgroundWorkPolicy.model_validate_json(json.dumps(body)).sha256() == policy.sha256()
    now = datetime.now(UTC)
    run = BackgroundRun(
        run_id=str(uuid4()),
        owner_id=policy.owner_id,
        project_id=policy.project_id,
        item_id=str(uuid4()),
        binding_sha256="ab" * 32,
        link_sha256="ab" * 32,
        account_observation_sha256="ab" * 32,
        identity_sha256="ab" * 32,
        profile_sha256="ab" * 32,
        binary_sha256="ab" * 32,
        quota_basis_sha256="ab" * 32,
        started_at=now,
        deadline=now + timedelta(seconds=30),
    )
    old = run.model_dump(mode="json")
    assert "model_ref" not in old and old["schema_version"] == 1
    assert BackgroundRun.model_validate_json(json.dumps(old)).sha256() == run.sha256()
    with pytest.raises(ValueError, match="background_run_model_version"):
        BackgroundRun.model_validate_json(json.dumps(old | {"model_ref": "claude-sonnet-5"}))


def test_selected_policy_requires_exact_model_plus_account_windows_and_deliberate_version():
    body = legacy()
    body.update(schema_version=2, model_ref="claude-sonnet-5")
    model_scope = {**body["quota_windows"][0], "model_ref": "claude-sonnet-5", "window_ref": "selected-model"}
    body["quota_windows"].append(model_scope)
    selected = BackgroundWorkPolicy.model_validate_json(json.dumps(body))
    assert selected.model_ref == "claude-sonnet-5" and selected.quota_windows[0].model_ref is None
    for changes in (
        {"schema_version": 1},
        {"model_ref": None},
        {"model_ref": "sonnet"},
        {"quota_windows": body["quota_windows"][:1]},
        {"quota_windows": [model_scope]},
        {"quota_windows": [body["quota_windows"][0], model_scope | {"model_ref": "claude-opus-5"}]},
    ):
        with pytest.raises(ValueError):
            BackgroundWorkPolicy.model_validate_json(json.dumps(body | changes))
