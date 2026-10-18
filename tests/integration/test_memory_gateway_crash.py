"""Actual NativeToolGateway+PG+Docker controller death, fixed synthetic scripts."""

import hashlib
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

from panestria.contracts.native_tools import ToolRequest, ToolScope
from panestria.execution.tool_authority import DurableToolAuthority, tool_binding
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.invocations import InvocationService
from panestria.kernel.leases import LeaseService
from panestria.kernel.sandbox_launches import SandboxLaunchService
from panestria.kernel.uow import UnitOfWork
from panestria.sandbox.native_tool_gateway import NativeCommandRegistry, ReviewedCommand, ToolPermit
from panestria.sandbox.profiles import SandboxProfile
from panestria.sandbox.runner import DockerSandbox, SandboxLaunchReference
from sandbox_launch_support import docker, exists, stopped_container

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("phase", ["claim", "intent", "created", "running"])
@pytest.mark.parametrize("revoked", [False, True])
def test_actual_gateway_crash_has_only_exact_durable_runtime_recovery(
    r1_task, tmp_path, phase, revoked, record_property
):
    actor = Actor(r1_task["owner"], r1_task["project"])

    def connect():
        return psycopg.connect(
            r1_task["dsn"], connect_timeout=1, options="-c statement_timeout=500 -c lock_timeout=500"
        )

    with connect() as c:
        lease = LeaseService().acquire(
            UnitOfWork(c), actor, r1_task["task"], "memory-gateway-crash", 0, ttl_seconds=120
        )
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
    workspace = root / "candidate"
    workspace.mkdir(parents=True, mode=0o700)
    script = tmp_path / "fixed-memory-check.py"
    script.write_text(
        "from pathlib import Path\nimport time\n"
        "assert not Path('/runtime/native-command.py').exists()\n"
        "assert not Path('/runtime/native-request.json').exists()\n"
        "with Path('/workspace/executed').open('a') as f:f.write('PUBLIC_EXECUTED\\n')\n"
        "time.sleep(60)\n"
    )
    script.chmod(0o400)
    registry = NativeCommandRegistry(
        (ReviewedCommand("memory-crash-check", script, hashlib.sha256(script.read_bytes()).hexdigest(), "edit"),)
    )
    request = ToolRequest(request_id=uuid4(), command_ref="memory-crash-check", payload_json='{"public":"fixture"}')
    profile = SandboxProfile(uid=os.getuid(), gid=os.getgid(), wall_seconds=15, stdin_mode="native-frame-v1")
    permit = ToolPermit(scope, request.sha256(), registry.sha256(), workspace, profile, time.monotonic() + 15)
    binding = tool_binding(permit)
    with connect() as c:
        identity = InvocationService().prepare(UnitOfWork(c), actor, binding, "actual-memory-gateway-death")
    ready = tmp_path / "barrier.json"
    config = tmp_path / "controller.json"
    config.write_text(
        json.dumps(
            {
                "dsn": r1_task["dsn"],
                "owner": actor.owner_id,
                "project": actor.project_id,
                "scope": scope.model_dump(mode="json"),
                "request": request.model_dump(mode="json"),
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
        [sys.executable, str(ROOT / "tests/fixtures/memory_gateway_child.py"), str(config)],
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
        until = time.monotonic() + 12
        while True:
            assert child.poll() is None and time.monotonic() < until, "actual_memory_gateway_barrier_unavailable"
            if phase != "running" and ready.exists():
                witness = json.loads(ready.read_text())
                assert witness == {"phase": phase, "mounts": ["/runtime/native-launch.py", "/runtime/native-input.py"]}
                break
            if phase == "running" and (workspace / "executed").exists():
                assert (workspace / "executed").read_text() == "PUBLIC_EXECUTED\n"
                break
            time.sleep(0.02)
        matches = []
        if phase == "claim":
            with connect() as c:
                assert c.execute(
                    "SELECT count(*) FROM panestria.worker_invocation_launch WHERE invocation_id=%s", (identity,)
                ).fetchone() == (0,)
        else:
            with connect() as c:
                intent = SandboxLaunchService().read(UnitOfWork(c), actor, binding, identity)
            matches = docker(
                "ps", "--all", "--quiet", "--no-trunc", "--filter", "label=panestria.launch=" + str(intent.launch_id)
            ).splitlines()
            if phase == "intent":
                assert matches == []
            else:
                assert len(matches) == 1
                actual = json.loads(docker("inspect", matches[0]))[0]
                assert actual["State"]["Status"] == ("created" if phase == "created" else "running")
                assert actual["Config"]["OpenStdin"] and actual["Config"]["StdinOnce"]
                destinations = {m["Destination"] for m in actual["Mounts"] if m["Type"] == "bind"}
                assert destinations == {
                    "/workspace",
                    "/runtime/native-launch.py",
                    "/runtime/native-input.py",
                    "/runtime/panestria-no-network.py",
                }
                assert str(script) not in {m["Source"] for m in actual["Mounts"]}
        child.kill()
        assert child.wait(timeout=5) == -9
        if revoked:
            with connect() as c:
                LeaseService().release(UnitOfWork(c), actor, lease.attempt_id, lease.epoch)
        with connect() as c:
            before_state = c.execute("SELECT state FROM panestria.task WHERE id=%s", (r1_task["task"],)).fetchone()
            before_approvals = c.execute(
                "SELECT id,state,effect_digest FROM panestria.approval_request WHERE goal_id=%s ORDER BY id",
                (r1_task["goal"],),
            ).fetchall()
        with stopped_container(
            name="panestria-unrelated-memory-" + uuid4().hex,
            labels={
                "panestria.purpose": "worker",
                "panestria.attempt": str(scope.attempt_id),
                "panestria.launch": str(uuid4()),
            },
        ) as unrelated:
            if intent is None:
                # Historical one-use recovery closes a claimed pre-launch call;
                # no absence observation mints execution or retry authority.
                with connect() as c:
                    InvocationService().finish(UnitOfWork(c), actor, binding, identity, None)
            else:
                observed = DurableToolAuthority(connect, actor, identity).reconcile_launch(permit, root)
                assert observed.status == ("NOT_OBSERVED" if phase == "intent" else "REMOVED")
            assert exists(unrelated) and all(not exists(identifier) for identifier in matches)
            with connect() as c:
                assert c.execute(
                    "SELECT state,receipt_sha256 FROM panestria.worker_invocation WHERE id=%s", (identity,)
                ).fetchone() == ("UNKNOWN", None)
                with pytest.raises(KernelDenied), c.transaction():
                    InvocationService().claim(UnitOfWork(c), actor, binding, identity)
                assert (
                    c.execute("SELECT state FROM panestria.task WHERE id=%s", (r1_task["task"],)).fetchone()
                    == before_state
                )
                assert (
                    c.execute(
                        "SELECT id,state,effect_digest FROM panestria.approval_request WHERE goal_id=%s ORDER BY id",
                        (r1_task["goal"],),
                    ).fetchall()
                    == before_approvals
                )
        assert (workspace / "executed").exists() == (phase == "running")
        if phase == "running":
            assert (workspace / "executed").read_text() == "PUBLIC_EXECUTED\n"
        record_property("scope", "actual memory NativeToolGateway+PG+Docker+SIGKILL; fixed scripts, no vendor auth")
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
