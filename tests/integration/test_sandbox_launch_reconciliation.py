"""Real owned Docker resources with injected lost replies; no provider, owner DB or secrets."""

import json
from dataclasses import replace
from uuid import UUID, uuid4

import pytest

from panestria.sandbox.profiles import DEFAULT_IMAGE, SandboxRejected
from panestria.sandbox.runner import DockerSandbox, SandboxLaunchReference, SandboxLaunchUncertain
from sandbox_launch_support import FaultyCreate, docker, exists, setup, stopped_container

COMMAND = ("/usr/local/bin/python", "-c", "from pathlib import Path;Path('/workspace/executed').write_text('once')")


@pytest.mark.parametrize("reply", ["error", "malformed"])
def test_actual_created_container_is_removed_after_injected_lost_or_malformed_reply(tmp_path, reply, record_property):
    root, workspace, profile = setup(tmp_path)
    runner = FaultyCreate(root, reply=reply)
    try:
        with pytest.raises(SandboxLaunchUncertain) as caught:
            runner.run(workspace, COMMAND, profile)
        assert len(runner.created) == 1 and runner.executed == 0 and not (workspace / "executed").exists()
        assert caught.value.reference == runner.references[0]
        assert caught.value.reconciliation.status == "REMOVED"
        assert caught.value.reconciliation.container_id == runner.created[0] and not exists(runner.created[0])
        assert str(caught.value) == "sandbox_launch_reconciliation_required"
        record_property("scope", "actual stopped Docker create/remove; injected reply fault, not a real daemon outage")
    finally:
        runner.cleanup_fixture()


def test_foreign_returned_container_id_is_preserved_while_actual_own_launch_is_removed(tmp_path):
    root, workspace, profile = setup(tmp_path)
    with stopped_container(
        name="panestria-foreign-reply-" + uuid4().hex, labels={"panestria.purpose": "fixture"}
    ) as foreign:
        runner = FaultyCreate(root, reply="foreign", foreign=foreign)
        try:
            with pytest.raises(SandboxLaunchUncertain) as caught:
                runner.run(workspace, COMMAND, profile)
            assert runner.executed == 0 and caught.value.reconciliation.status == "REMOVED"
            assert exists(foreign) and not exists(runner.created[0])
        finally:
            runner.cleanup_fixture()


def test_real_name_collision_and_same_attempt_do_not_authorize_foreign_cleanup(tmp_path):
    root, workspace, profile = setup(tmp_path)
    attempt = uuid4()
    labels = {
        "panestria.purpose": "worker",
        "panestria.attempt": str(attempt),
        "panestria.launch": str(uuid4()),
        "panestria.profile": profile.sha256(),
    }
    with stopped_container(name="panestria-worker-" + attempt.hex, labels=labels) as foreign:
        with pytest.raises(SandboxLaunchUncertain) as caught:
            DockerSandbox(root).run(workspace, COMMAND, profile, attempt_id=str(attempt))
        assert caught.value.reconciliation.status == "NOT_OBSERVED" and exists(foreign)
        assert caught.value.reference.launch_id != labels["panestria.launch"]
        assert not (workspace / "executed").exists()


@pytest.mark.parametrize("field", ["attempt", "purpose", "profile", "name", "image", "expected-id"])
def test_real_candidate_with_matching_nonce_but_other_identity_is_not_removed(tmp_path, field):
    root, _, profile = setup(tmp_path)
    image_id = json.loads(docker("image", "inspect", DEFAULT_IMAGE))[0]["Id"]
    reference = SandboxLaunchReference(str(uuid4()), str(uuid4()), profile.sha256(), image_id)
    labels = {
        "panestria.purpose": "worker",
        "panestria.attempt": reference.attempt_id,
        "panestria.launch": reference.launch_id,
        "panestria.profile": reference.profile_sha256,
    }
    name = reference.name
    if field in {"attempt", "purpose", "profile"}:
        labels["panestria." + field] = str(uuid4()) if field == "attempt" else "unrelated-fixture"
    elif field == "name":
        name += "-foreign"
    elif field == "image":
        reference = replace(reference, image_id="sha256:" + "0" * 64)
    with stopped_container(name=name, labels=labels) as identifier:
        result = DockerSandbox(root).reconcile_launch(
            reference, expected_container_id="0" * 64 if field == "expected-id" else None
        )
        assert result.status == "UNCONFIRMED" and exists(identifier)


def test_multiple_actual_candidates_sharing_nonce_are_preserved(tmp_path):
    root, _, profile = setup(tmp_path)
    image_id = json.loads(docker("image", "inspect", DEFAULT_IMAGE))[0]["Id"]
    reference = SandboxLaunchReference(str(uuid4()), str(uuid4()), profile.sha256(), image_id)
    labels = {
        "panestria.purpose": "worker",
        "panestria.attempt": reference.attempt_id,
        "panestria.launch": reference.launch_id,
        "panestria.profile": reference.profile_sha256,
    }
    with stopped_container(name=reference.name, labels=labels) as first:
        with stopped_container(name=reference.name + "-duplicate", labels=labels) as second:
            observed = DockerSandbox(root).reconcile_launch(reference)
            assert observed.status == "UNCONFIRMED" and exists(first) and exists(second)


def test_query_failure_remains_unconfirmed_until_later_exact_reconciliation(tmp_path):
    root, workspace, profile = setup(tmp_path)
    runner = FaultyCreate(root, query_error=True)
    try:
        with pytest.raises(SandboxLaunchUncertain) as caught:
            runner.run(workspace, COMMAND, profile)
        assert caught.value.reconciliation.status == "UNCONFIRMED" and exists(runner.created[0])
        later = DockerSandbox(root).reconcile_launch(caught.value.reference)
        assert later.status == "REMOVED" and later.container_id == runner.created[0]
        assert runner.executed == 0 and not exists(runner.created[0])
        assert DockerSandbox(root).reconcile_launch(caught.value.reference).status == "NOT_OBSERVED"
    finally:
        runner.cleanup_fixture()


@pytest.mark.parametrize("reply", ["error", "normal"])
@pytest.mark.parametrize("remove_error", ["before", "after"])
def test_lost_remove_reply_never_returns_a_success_or_repeats_actual_execution(tmp_path, reply, remove_error):
    root, workspace, profile = setup(tmp_path)
    runner = FaultyCreate(root, reply=reply, remove_error=remove_error)
    try:
        with pytest.raises(SandboxLaunchUncertain) as caught:
            runner.run(workspace, COMMAND, profile)
        assert caught.value.reconciliation.status == "UNCONFIRMED"
        assert exists(runner.created[0]) == (remove_error == "before")
        assert runner.executed == (1 if reply == "normal" else 0)
        if reply == "normal":
            assert (workspace / "executed").read_text() == "once"
        else:
            assert not (workspace / "executed").exists()
        later = DockerSandbox(root).reconcile_launch(caught.value.reference)
        assert later.status == ("REMOVED" if remove_error == "before" else "NOT_OBSERVED")
        assert not exists(runner.created[0])
        assert len(runner.created) == 1
    finally:
        runner.cleanup_fixture()


def test_successive_normal_launches_get_distinct_nonce_and_exact_cleanup(tmp_path):
    root, workspace, profile = setup(tmp_path)
    runner = FaultyCreate(root, reply="normal")
    identity = str(uuid4())
    try:
        for _ in range(2):
            result = runner.run(
                workspace, ("/usr/local/bin/python", "-c", "print('PUBLIC_FIXTURE')"), profile, attempt_id=identity
            )
            assert result.reason == "completed" and result.exit_code == 0 and b"PUBLIC_FIXTURE" in result.output
        assert len({ref.launch_id for ref in runner.references}) == 2
        assert all(ref.attempt_id == identity and UUID(ref.launch_id).version == 4 for ref in runner.references)
        assert runner.executed == 2 and all(not exists(identifier) for identifier in runner.created)
    finally:
        runner.cleanup_fixture()


def test_not_observed_does_not_hide_a_later_actual_create_or_authorize_a_retry(tmp_path):
    root, workspace, profile = setup(tmp_path)
    pending = []

    class DelayedCreate(DockerSandbox):
        def _docker(self, args, *, timeout=30):
            if args[0] == "create":
                pending.append(args)
                raise SandboxRejected("container_runtime_unavailable")
            return super()._docker(args, timeout=timeout)

    # Explicit injected client failure, followed by an actual delayed daemon-side
    # create using the original exact arguments; no process is started or rerun.
    with pytest.raises(SandboxLaunchUncertain) as caught:
        DelayedCreate(root).run(workspace, COMMAND, profile)
    assert caught.value.reconciliation.status == "NOT_OBSERVED" and len(pending) == 1
    identifier = docker(*pending[0]).strip()
    try:
        actual = json.loads(docker("inspect", identifier))[0]
        assert actual["State"]["Status"] == "created" and not (workspace / "executed").exists()
        observed = DockerSandbox(root).reconcile_launch(caught.value.reference)
        assert observed.status == "REMOVED" and observed.container_id == identifier and not exists(identifier)
    finally:
        if exists(identifier):
            actual = json.loads(docker("inspect", identifier))[0]
            assert DockerSandbox._owned_launch(actual, identifier, caught.value.reference)
            docker("rm", "--force", "--volumes", identifier)
