"""Closed metadata and scope-preserving runtime profile guards; no provider/DB/Docker."""

import time
from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from panestria.contracts.native_tools import ToolScope
from panestria.contracts.sandbox_launch import SandboxLaunchIntent, SandboxLaunchObservation
from panestria.execution.tool_authority import DurableToolAuthority
from panestria.kernel.goals import Actor
from panestria.sandbox.native_tool_gateway import ToolPermit
from panestria.sandbox.profiles import SandboxProfile
from panestria.sandbox.runner import SandboxLaunchReference


def intent():
    return SandboxLaunchIntent(
        invocation_id=uuid4(),
        binding_sha256="a" * 64,
        scope_sha256="b" * 64,
        runtime_attempt_id=uuid4(),
        launch_id=uuid4(),
        profile_sha256="c" * 64,
        image_id="sha256:" + "d" * 64,
    )


def test_closed_metadata_roundtrip_is_canonical_and_accepts_no_payload_paths_or_credentials():
    value = intent()
    assert SandboxLaunchIntent.model_validate_json(value.model_dump_json()).sha256() == value.sha256()
    for field in ("prompt", "workspace", "credentials", "environment", "argv"):
        with pytest.raises(ValidationError):
            SandboxLaunchIntent.model_validate({**value.model_dump(), field: "SYNTHETIC_FORBIDDEN_CONTENT"})


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", True),
        ("schema_version", 1.0),
        ("schema_version", 2),
        ("launch_id", UUID("00000000-0000-1000-8000-000000000001")),
        ("image_id", "latest"),
        ("profile_sha256", "0" * 63),
    ],
)
def test_malformed_version_identity_and_pins_are_rejected(field, value):
    with pytest.raises(ValidationError):
        SandboxLaunchIntent.model_validate({**intent().model_dump(), field: value})


@pytest.mark.parametrize(
    "status,reason,cid",
    [
        ("REMOVED", "owned_container_removed", None),
        ("NOT_OBSERVED", "no_owned_container_observed", "a" * 64),
        ("UNCONFIRMED", "owned_container_removed", "a" * 64),
        ("REMOVED", "launch_runtime_unconfirmed", "a" * 64),
        ("UNCONFIRMED", "SYNTHETIC_PRIVATE_DIAGNOSTIC", None),
    ],
)
def test_observation_cannot_claim_success_from_unknown_or_leak_diagnostics(status, reason, cid):
    with pytest.raises(ValidationError):
        SandboxLaunchObservation(intent_sha256="a" * 64, status=status, reason=reason, container_id=cid)


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", "mock-no-network"),
        ("image", "python@sha256:" + "f" * 64),
        ("uid", 2000),
        ("gid", 2000),
        ("memory_bytes", 1024**3),
        ("cpu_nanos", 2_000_000_000),
        ("pids", 64),
        ("output_bytes", 262144),
        ("tmp_bytes", 64 * 1024**2),
        ("wall_seconds", 31),
        ("wall_seconds", True),
        ("wall_seconds", "10"),
        ("wall_seconds", float("nan")),
    ],
)
def test_actual_profile_can_only_reduce_time_never_change_scope_or_other_caps(tmp_path, field, value):
    scope = ToolScope(
        owner_id=uuid4(),
        project_id=uuid4(),
        task_id=uuid4(),
        attempt_id=uuid4(),
        lease_epoch=1,
        contract_sha256="a" * 64,
        policy_ref="test-policy-v1",
    )
    profile = SandboxProfile(name="restricted-offline")
    permit = ToolPermit(scope, "b" * 64, "c" * 64, tmp_path, profile, time.monotonic() + 30)
    actual = replace(profile, **{field: value})
    reference = SandboxLaunchReference(str(uuid4()), str(uuid4()), actual.sha256(), "sha256:" + "d" * 64)

    def forbidden():
        raise AssertionError("widened_profile_reached_database")

    authority = DurableToolAuthority(forbidden, Actor(str(scope.owner_id), str(scope.project_id)), str(uuid4()))
    with pytest.raises(ValueError, match="sandbox_launch_profile_mismatch"):
        authority.record_launch(permit, reference, actual)
