"""A worker that exits within its wall budget keeps its own outcome when the attach EOF is late."""

from __future__ import annotations

import subprocess
import sys
import time
from datetime import UTC, datetime

import pytest

import panestria.sandbox.runner as runner
from panestria.sandbox.profiles import SandboxProfile
from panestria.sandbox.runner import DockerSandbox

CID = "ab" * 32
WALL = 0.3


def docker_time(seconds: float) -> str:
    """Format like the daemon: nanosecond precision, UTC 'Z' suffix."""
    return f"{datetime.fromtimestamp(seconds, UTC):%Y-%m-%dT%H:%M:%S.%f}000Z"


def late_attach(monkeypatch, program):
    """A real attach client whose output and exit trail the worker's exit."""
    real_popen = subprocess.Popen
    children, launched = [], []

    def attach(args, *rest, **kwargs):
        assert list(args[:3]) == ["docker", "start", "--attach"]
        launched.append(time.time())
        child = real_popen([sys.executable, "-I", "-c", program], stdout=kwargs["stdout"], stderr=kwargs["stderr"])
        children.append(child)
        return child

    monkeypatch.setattr(runner.subprocess, "Popen", attach)
    return children, launched


def exited(code: int, finished: str, status: str = "exited") -> dict:
    return {"Running": False, "Status": status, "ExitCode": code, "OOMKilled": False, "FinishedAt": finished}


class ReportedState(DockerSandbox):
    """The daemon's view is scripted; nothing here may kill the stopped worker."""

    def __init__(self, root, state):
        super().__init__(root)
        self.state, self.inspections = state, 0

    def _inspect(self, identifier):
        assert identifier == CID
        self.inspections += 1
        return {"State": self.state()}

    def _docker(self, args, **kwargs):
        raise AssertionError("a worker that already exited must not be killed")


def test_exit_within_budget_with_late_attach_eof_keeps_the_workers_own_failure(tmp_path, monkeypatch):
    # Under host load the attach EOF trailed the worker's exit by up to 2.4 s,
    # past the deadline; the runner then reported deadline_exceeded for a
    # worker that had already failed by itself (exit 7) inside its budget.
    monkeypatch.setattr(runner, "LATE_OUTPUT_SECONDS", 60.0)
    children, launched = late_attach(
        monkeypatch, "import os,sys,time;time.sleep(1.0);os.write(1,b'LATE_OUTPUT');time.sleep(0.2);sys.exit(7)"
    )
    sandbox = ReportedState(tmp_path, lambda: exited(7, docker_time(launched[0])))
    try:
        receipt = sandbox._execute(CID, SandboxProfile(wall_seconds=WALL), "cd" * 32)
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=5)
    assert receipt.reason == "process_failed" and receipt.exit_code == 7
    assert receipt.output == b"LATE_OUTPUT" and receipt.elapsed_seconds > WALL
    assert children[0].returncode == 7  # The attach client ran to its own end.


@pytest.mark.parametrize(
    "case",
    ["exited_after_budget", "never_started", "unreadable_exit_time", "naive_exit_time"],
)
def test_deadline_stands_unless_the_daemon_shows_an_exit_inside_the_budget(tmp_path, monkeypatch, case):
    children, launched = late_attach(monkeypatch, "import sys,time;time.sleep(30);sys.exit(7)")

    def state():
        if case == "exited_after_budget":  # Stopped by itself, but only after its deadline.
            return exited(7, docker_time(launched[0] + WALL + 0.2))
        if case == "never_started":
            return exited(0, "0001-01-01T00:00:00Z", status="created")
        if case == "unreadable_exit_time":
            return exited(7, "not-a-time")
        return exited(7, docker_time(launched[0]).removesuffix("Z"))  # No zone: not comparable.

    started = time.monotonic()
    try:
        receipt = ReportedState(tmp_path, state)._execute(CID, SandboxProfile(wall_seconds=WALL), "cd" * 32)
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=5)
    assert receipt.reason == "deadline_exceeded"
    assert children[0].returncode == -9 and time.monotonic() - started < 10  # Only the attach client was stopped.


def test_attach_output_still_open_after_the_late_window_ends_as_a_deadline(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "LATE_OUTPUT_SECONDS", 0.3)
    children, launched = late_attach(monkeypatch, "import sys,time;time.sleep(30);sys.exit(0)")
    sandbox = ReportedState(tmp_path, lambda: exited(0, docker_time(launched[0])))
    started = time.monotonic()
    try:
        receipt = sandbox._execute(CID, SandboxProfile(wall_seconds=WALL), "cd" * 32)
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=5)
    assert receipt.reason == "deadline_exceeded" and receipt.exit_code == 0
    assert children[0].returncode == -9 and time.monotonic() - started < 10


def test_worker_still_running_at_the_deadline_is_killed_as_before(tmp_path, monkeypatch):
    children, _ = late_attach(monkeypatch, "import sys,time;time.sleep(30);sys.exit(0)")
    killed = []

    class RunningState(DockerSandbox):
        def _inspect(self, identifier):
            if not killed:
                return {"State": {"Running": True, "Status": "running", "FinishedAt": "0001-01-01T00:00:00Z"}}
            return {"State": exited(137, docker_time(time.time()))}

        def _docker(self, args, **kwargs):
            assert args == ["kill", CID] and not killed
            killed.append(time.monotonic())
            children[0].kill()
            return subprocess.CompletedProcess(args, 0, "", "")

    try:
        receipt = RunningState(tmp_path)._execute(CID, SandboxProfile(wall_seconds=WALL), "cd" * 32)
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=5)
    assert receipt.reason == "deadline_exceeded" and receipt.exit_code == 137 and len(killed) == 1
