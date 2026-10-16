"""Actual native-tool controller admission/DB/Docker, no vendor CLI or inference."""

import json

import pytest
from test_registered_check_authority import configured as configured
from test_registered_check_authority import run

from panestria.execution import registered_checks as checks
from panestria.execution.tool_authority import DurableToolAuthority
from panestria.kernel.leases import LeaseService
from panestria.kernel.uow import UnitOfWork
from panestria.sandbox.runner import DockerSandbox
from sandbox_launch_support import docker


@pytest.mark.parametrize("fault", ["intent-ack", "start-revocation"])
def test_actual_registered_controller_never_starts_after_uncertain_intent_or_revoked_start(
    configured, monkeypatch, fault
):
    task, args = configured
    controller = checks.RegisteredCheckController(*args)
    calls, captured = [], {}
    actual_docker = DockerSandbox._docker

    def trace(self, argv, **kwargs):
        calls.append(argv[0])
        return actual_docker(self, argv, **kwargs)

    monkeypatch.setattr(DockerSandbox, "_docker", trace)
    if fault == "intent-ack":
        original = checks._ReadAuthority.record_launch

        def lost_ack(self, permit, reference, profile):
            original(self, permit, reference, profile)
            captured.update(authority=self, permit=permit, reference=reference)
            raise OSError("SYNTHETIC_COMMIT_ACK_LOST")

        monkeypatch.setattr(checks._ReadAuthority, "record_launch", lost_ack)
    else:
        original_factory = checks._ReadAuthority.runner_factory

        def factory(self, permit):
            captured.update(authority=self, permit=permit)
            make = original_factory(self, permit)

            def runner(root, mounts):
                value = make(root, mounts)
                start = value._before_start

                def revoke_before_start():
                    with controller.connect() as c:
                        LeaseService().release(
                            UnitOfWork(c),
                            controller.actor,
                            str(controller.scope.attempt_id),
                            controller.scope.lease_epoch,
                        )
                    start()

                value._before_start = revoke_before_start
                return value

            return runner

        monkeypatch.setattr(checks._ReadAuthority, "runner_factory", factory)
    result = run(controller)
    assert result.outcome == "UNKNOWN" and "start" not in calls
    assert calls.count("create") == (0 if fault == "intent-ack" else 1)
    authority = captured["authority"]
    with controller.connect() as c:
        row = c.execute(
            "SELECT state,receipt_sha256 FROM panestria.worker_invocation WHERE id=%s", (authority.identity,)
        ).fetchone()
        assert row == ("UNKNOWN", None)
        record = c.execute(
            "SELECT launch_id::text FROM panestria.worker_invocation_launch WHERE invocation_id=%s",
            (authority.identity,),
        ).fetchone()
        assert record is not None
        events = c.execute("SELECT payload FROM panestria.task_event WHERE task_id=%s", (task["task"],)).fetchall()
        assert "SYNTHETIC_COMMIT_ACK_LOST" not in json.dumps(events)
    assert not docker("ps", "--all", "--quiet", "--filter", "label=panestria.launch=" + record[0]).strip()
    reconstructed = DurableToolAuthority(controller.connect, controller.actor, authority.identity)
    observed = reconstructed.reconcile_launch(captured["permit"], controller.snapshot.directory.parent)
    assert observed.status == "NOT_OBSERVED"
    before = calls.count("create")
    assert run(checks.RegisteredCheckController(*args)).outcome == "UNKNOWN"
    assert calls.count("create") == before
