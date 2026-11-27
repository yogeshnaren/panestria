"""A memory-limit kill is classified from the kernel's own cgroup v2 count.

Docker can stop a memory-killed worker with OOMKilled false: containerd's OOM
event is lost when the cgroup is removed first. The runner reads the kernel's
oom_kill counter from the container's cgroup while it exists. These tests use a
real SIGKILLed child behind the attach seam and a synthetic cgroup tree; the
Docker state always reports OOMKilled false, as on the failing hosts.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time

import pytest

import panestria.sandbox.runner as runner
from panestria.sandbox.profiles import SandboxProfile
from panestria.sandbox.runner import DockerSandbox

CID = "ab" * 32
SELF_KILL = "import os,signal,time;time.sleep({delay});os.kill(os.getpid(),signal.SIGKILL)"
SLEEP = "import time;time.sleep(60)"
LAYOUTS = {
    "systemd": ("system.slice", f"docker-{CID}.scope"),
    "cgroupfs": ("docker", CID),
}


def events(oom_kill: int) -> str:
    return f"low 0\nhigh 0\nmax {35 if oom_kill else 0}\noom {oom_kill}\noom_kill {oom_kill}\noom_group_kill 0\n"


@pytest.fixture
def cgroup(tmp_path, monkeypatch):
    root = tmp_path / "cgroup"
    monkeypatch.setattr(runner, "CGROUP_ROOT", root)
    monkeypatch.setattr(runner, "OOM_SETTLE_DELAYS", (0.01,))

    def create(oom_kill: int, layout: str = "systemd"):
        path = root.joinpath(*LAYOUTS[layout], "memory.events")
        path.parent.mkdir(parents=True)
        path.write_text(events(oom_kill))
        return path

    return create


def run(tmp_path, monkeypatch, program: str, *, wall_seconds: float = 5, cancel_after: float | None = None):
    """Run a real child as the attach process; Docker never reports an OOM."""
    real_popen = subprocess.Popen
    children: list[subprocess.Popen[bytes]] = []

    def attach(*args, **kwargs):
        child = real_popen([sys.executable, "-I", "-c", program], stdin=kwargs["stdin"], stdout=kwargs["stdout"])
        children.append(child)
        return child

    def state() -> dict:
        code = children[0].poll()
        return {
            "Running": code is None,
            "Status": "running" if code is None else "exited",
            "ExitCode": 0 if code is None else (128 - code if code < 0 else code),
            "OOMKilled": False,
        }

    class Unreported(DockerSandbox):
        def _inspect(self, identifier):
            return {"Id": identifier, "State": state()}

        def _docker(self, args, **kwargs):
            if args == ["kill", CID]:  # The runner's own deadline/cancel kill.
                children[0].kill()
                children[0].wait(timeout=3)
                return subprocess.CompletedProcess(args, 0, "", "")
            assert args == ["inspect", CID]  # Bounded settlement rereads only.
            return subprocess.CompletedProcess(args, 0, json.dumps([{"Id": CID, "State": state()}]), "")

    monkeypatch.setattr("panestria.sandbox.runner.subprocess.Popen", attach)
    cancel = threading.Event()
    timer = threading.Timer(cancel_after, cancel.set) if cancel_after is not None else None
    if timer:
        timer.start()
    try:
        return Unreported(tmp_path)._execute(CID, SandboxProfile(wall_seconds=wall_seconds), "cd" * 32, cancel=cancel)
    finally:
        if timer:
            timer.cancel()
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=3)


@pytest.mark.parametrize("layout", sorted(LAYOUTS))
def test_lost_docker_oom_event_is_classified_from_the_cgroup_count(tmp_path, monkeypatch, cgroup, layout):
    cgroup(1, layout)
    receipt = run(tmp_path, monkeypatch, SELF_KILL.format(delay=0.2))
    assert receipt.exit_code == 137 and receipt.oom_killed is False  # Docker's own report is kept.
    assert receipt.cgroup_oom_kills == 1 and receipt.reason == "memory_limit"


def test_count_is_read_while_the_worker_runs(tmp_path, monkeypatch, cgroup):
    path = cgroup(0)
    timer = threading.Timer(0.2, path.write_text, (events(1),))
    timer.start()
    try:
        receipt = run(tmp_path, monkeypatch, SELF_KILL.format(delay=0.5))
    finally:
        timer.cancel()
    assert receipt.oom_killed is False and receipt.cgroup_oom_kills == 1 and receipt.reason == "memory_limit"


@pytest.mark.parametrize("count", [0, None])
def test_sigkill_without_a_counted_oom_kill_stays_process_failed(tmp_path, monkeypatch, cgroup, count):
    if count is not None:
        cgroup(count)
    receipt = run(tmp_path, monkeypatch, SELF_KILL.format(delay=0.1))
    assert receipt.exit_code == 137 and receipt.oom_killed is False
    assert receipt.cgroup_oom_kills == count and receipt.reason == "process_failed"


@pytest.mark.parametrize("count", [0, None])
@pytest.mark.parametrize("stop,expected", [("deadline", "deadline_exceeded"), ("cancel", "cancelled")])
def test_runner_kills_keep_their_reasons(tmp_path, monkeypatch, cgroup, count, stop, expected):
    if count is not None:
        cgroup(count)
    started = time.monotonic()
    if stop == "deadline":
        receipt = run(tmp_path, monkeypatch, SLEEP, wall_seconds=0.5)
    else:
        receipt = run(tmp_path, monkeypatch, SLEEP, cancel_after=0.3)
    assert receipt.exit_code == 137 and receipt.cgroup_oom_kills == count and receipt.reason == expected
    assert time.monotonic() - started < 3


def test_watch_thread_does_not_outlive_the_run(tmp_path, monkeypatch, cgroup):
    cgroup(1)
    before = {thread.ident for thread in threading.enumerate()}
    run(tmp_path, monkeypatch, SELF_KILL.format(delay=0.1))
    assert {thread.ident for thread in threading.enumerate()} <= before
