"""Actual PG+Docker+controller SIGKILL; fixed public synthetic script, no inference."""

import json
import os
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest

from panestria.contracts.native_tools import ToolScope
from panestria.execution.tool_authority import DurableToolAuthority, tool_binding
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.invocations import InvocationService
from panestria.kernel.leases import LeaseService
from panestria.kernel.sandbox_launches import SandboxLaunchService
from panestria.kernel.uow import UnitOfWork
from panestria.sandbox.native_tool_gateway import ToolPermit
from panestria.sandbox.profiles import ReadOnlyMount, SandboxProfile, SandboxRejected
from panestria.sandbox.runner import DockerSandbox, SandboxLaunchReference
from sandbox_launch_support import docker, exists, stopped_container

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("phase", ["intent", "created", "running"])
@pytest.mark.parametrize("revoked", [False, True])
def test_reconstructed_controller_recovers_exact_resource_after_actual_process_death(
    r1_task, tmp_path, phase, revoked, record_property
):
    actor = Actor(r1_task["owner"], r1_task["project"])
    with psycopg.connect(r1_task["dsn"]) as c:
        lease = LeaseService().acquire(UnitOfWork(c), actor, r1_task["task"], "crash-fixture", 0, ttl_seconds=120)
    scope = ToolScope(
        owner_id=UUID(actor.owner_id),
        project_id=UUID(actor.project_id),
        task_id=UUID(r1_task["task"]),
        attempt_id=UUID(lease.attempt_id),
        lease_epoch=lease.epoch,
        contract_sha256="ab" * 32,
        policy_ref="test-policy-v1",
    )
    root = tmp_path / "attempts"
    root.mkdir(mode=0o700)
    workspace = root / "candidate"
    workspace.mkdir(mode=0o700)
    script = tmp_path / "fixed-check.py"
    script.write_text(
        "from pathlib import Path\nimport time\n"
        "with Path('/workspace/executed').open('a') as file:file.write('PUBLIC_EXECUTED\\n')\n"
        "time.sleep(20)\n"
    )
    script.chmod(0o400)
    profile = SandboxProfile(uid=os.getuid(), gid=os.getgid(), wall_seconds=10)
    permit = ToolPermit(scope, "c" * 64, "d" * 64, workspace, profile, time.monotonic() + 10)
    binding = tool_binding(permit)

    def connect():
        return psycopg.connect(
            r1_task["dsn"], connect_timeout=1, options="-c statement_timeout=500 -c lock_timeout=500"
        )

    with connect() as c:
        identity = InvocationService().prepare(UnitOfWork(c), actor, binding, "actual-controller-death")
    ready = tmp_path / "barrier-ready"
    config = tmp_path / "synthetic-controller.json"
    config.write_text(
        json.dumps(
            {
                "dsn": r1_task["dsn"],
                "owner": actor.owner_id,
                "project": actor.project_id,
                "scope": scope.model_dump(mode="json"),
                "request_sha256": permit.request_sha256,
                "registry_sha256": permit.registry_sha256,
                "profile": asdict(profile),
                "workspace": str(workspace),
                "root": str(root),
                "script": str(script),
                "ready": str(ready),
                "phase": phase,
                "invocation_id": identity,
            }
        )
    )
    config.chmod(0o600)
    child = subprocess.Popen(
        [sys.executable, str(ROOT / "tests/fixtures/durable_launch_child.py"), str(config)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(tmp_path),
            "PYTHONPATH": str(ROOT / "src"),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    )
    intent = None
    try:
        deadline = time.monotonic() + 12
        while True:
            assert child.poll() is None and time.monotonic() < deadline, "synthetic_controller_barrier_unavailable"
            if phase != "running" and ready.exists():
                break
            if (
                phase == "running"
                and (workspace / "executed").exists()
                and (workspace / "executed").read_text() == "PUBLIC_EXECUTED\n"
            ):
                break
            time.sleep(0.02)
        with connect() as c:
            intent = SandboxLaunchService().read(UnitOfWork(c), actor, binding, identity)
        matches = docker(
            "ps", "--all", "--quiet", "--no-trunc", "--filter", "label=panestria.launch=" + str(intent.launch_id)
        ).splitlines()
        if phase == "intent":
            assert matches == []
        else:
            assert len(matches) == 1
            state = json.loads(docker("inspect", matches[0]))[0]["State"]
            assert state["Status"] == ("created" if phase == "created" else "running")
        # Kill only this exact Popen-owned controller. Real runtime and Docker
        # resources remain independent of the dead Python process.
        child.kill()
        assert child.wait(timeout=5) == -9
        if revoked:
            with connect() as c:
                LeaseService().release(UnitOfWork(c), actor, lease.attempt_id, lease.epoch)
        labels = {
            "panestria.purpose": "worker",
            "panestria.attempt": str(intent.runtime_attempt_id),
            "panestria.launch": str(uuid4()),
        }
        with stopped_container(name="panestria-unrelated-crash-" + uuid4().hex, labels=labels) as unrelated:
            authority = DurableToolAuthority(connect, actor, identity)
            observed = authority.reconcile_launch(permit, root)
            assert observed.status == ("NOT_OBSERVED" if phase == "intent" else "REMOVED")
            assert exists(unrelated) and all(not exists(identifier) for identifier in matches)
            with connect() as c:
                assert c.execute(
                    "SELECT state,receipt_sha256 FROM panestria.worker_invocation WHERE id=%s", (identity,)
                ).fetchone() == ("UNKNOWN", None)
                with pytest.raises(KernelDenied), c.transaction():
                    InvocationService().claim(UnitOfWork(c), actor, binding, identity)
            rerun = authority.runner_factory(permit)(root, (ReadOnlyMount(script, "/runtime/crash-check.py"),))
            original = rerun._docker

            def no_create(args, **kwargs):
                assert args[0] != "create", "recovery_repeated_container_dispatch"
                return original(args, **kwargs)

            rerun._docker = no_create
            with pytest.raises(SandboxRejected, match="launch_intent_unconfirmed"):
                rerun.run(workspace, ("/usr/local/bin/python", "-I", "/runtime/crash-check.py"), profile)
        assert (workspace / "executed").exists() == (phase == "running")
        if phase == "running":
            assert (workspace / "executed").read_text() == "PUBLIC_EXECUTED\n"
        record_property(
            "scope", "actual PG+Docker+SIGKILL/direct runtime callback recovery; synthetic script, not native auth"
        )
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
        child.communicate(timeout=5)
        if intent is None:
            try:
                with connect() as c:
                    intent = SandboxLaunchService().read(UnitOfWork(c), actor, binding, identity)
            except KernelDenied:
                pass
        if intent is not None:
            reference = SandboxLaunchReference(
                str(intent.runtime_attempt_id), str(intent.launch_id), intent.profile_sha256, intent.image_id
            )
            for identifier in docker(
                "ps", "--all", "--quiet", "--no-trunc", "--filter", "label=panestria.launch=" + str(intent.launch_id)
            ).splitlines():
                assert DockerSandbox._owned_launch(json.loads(docker("inspect", identifier))[0], identifier, reference)
                docker("rm", "--force", "--volumes", identifier)
