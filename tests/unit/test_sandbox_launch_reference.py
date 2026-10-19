"""Controller reconciliation reference validation; no Docker or native execution."""

from dataclasses import replace
from uuid import uuid4

import pytest

from panestria.sandbox.profiles import SandboxRejected
from panestria.sandbox.runner import DockerSandbox, SandboxLaunchReference


@pytest.mark.parametrize(
    "field,value",
    [
        ("attempt_id", "not-a-uuid"),
        ("attempt_id", True),
        pytest.param("launch_id", "00000000-0000-1000-8000-000000000001", id="launch-id-wrong-uuid-version"),
        ("launch_id", "--all"),
        ("profile_sha256", "0" * 63),
        ("image_id", "latest"),
    ],
)
def test_invalid_reference_cannot_issue_runtime_lookup(tmp_path, monkeypatch, field, value):
    reference = SandboxLaunchReference(str(uuid4()), str(uuid4()), "a" * 64, "sha256:" + "b" * 64)
    reference = replace(reference, **{field: value})

    def forbidden(*args, **kwargs):
        raise AssertionError("invalid_reference_reached_docker")

    runner = DockerSandbox(tmp_path)
    monkeypatch.setattr(runner, "_docker", forbidden)
    with pytest.raises(SandboxRejected, match="invalid_launch_reference"):
        runner.reconcile_launch(reference)


@pytest.mark.parametrize("identifier", [True, "short-id", "--all", "0" * 63, "f" * 65])
def test_invalid_expected_id_cannot_select_cleanup_target(tmp_path, monkeypatch, identifier):
    reference = SandboxLaunchReference(str(uuid4()), str(uuid4()), "a" * 64, "sha256:" + "b" * 64)

    def forbidden(*args, **kwargs):
        raise AssertionError("invalid_id_reached_docker")

    runner = DockerSandbox(tmp_path)
    monkeypatch.setattr(runner, "_docker", forbidden)
    with pytest.raises(SandboxRejected, match="invalid_container_identity"):
        runner.reconcile_launch(reference, expected_container_id=identifier)
