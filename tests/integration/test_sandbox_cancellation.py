"""Cancellation and EOF require observed process/container termination."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from panestria.sandbox.profiles import SandboxProfile, SandboxRejected
from panestria.sandbox.runner import DockerSandbox


def test_pre_cancelled_worker_never_calls_docker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cancel = threading.Event()
    cancel.set()
    runner = DockerSandbox(tmp_path)

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("must not allocate a container")

    monkeypatch.setattr(runner, "_docker", forbidden)
    with pytest.raises(SandboxRejected, match="cancelled_before_start"):
        runner.run(tmp_path / "not-created", ("/usr/local/bin/python",), SandboxProfile(), cancel=cancel)


def test_attachment_eof_does_not_hide_a_running_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_popen = subprocess.Popen
    cancel = threading.Event()
    timer = threading.Timer(0.2, cancel.set)
    running = True

    class ObservedWorker(DockerSandbox):
        def _inspect(self, container_id: str) -> dict[str, object]:
            return {"State": {"Running": running, "ExitCode": 137, "OOMKilled": False}}

        def _docker(self, args: list[str], *, timeout: float = 30) -> subprocess.CompletedProcess[str]:
            nonlocal running
            assert args == ["kill", "ab" * 32]
            running = False
            return subprocess.CompletedProcess(args, 0, "", "")

    def detached(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        return real_popen(
            [sys.executable, "-I", "-c", "import os,time;os.close(1);os.close(2);time.sleep(20)"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

    monkeypatch.setattr("panestria.sandbox.runner.subprocess.Popen", detached)
    timer.start()
    started = time.monotonic()
    try:
        receipt = ObservedWorker(tmp_path)._execute(
            "ab" * 32, SandboxProfile(wall_seconds=15), "cd" * 32, cancel=cancel
        )
    finally:
        timer.cancel()
        timer.join()
    assert receipt.reason == "cancelled" and not running
    assert time.monotonic() - started < 3


@pytest.mark.docker_boundary
@pytest.mark.live
@pytest.mark.parametrize("close_output", [False, True])
def test_actual_worker_cancellation_stops_and_removes_only_its_container(
    tmp_path: Path,
    close_output: bool,
    record_property: pytest.RecordProperty,
) -> None:
    record_property("gate_case_id", "AOS-008-TC04")
    record_property("source_clauses", "AOS-008-F01,AOS-008-F02,AOS-008-AC04")
    record_property("execution_mode", "OS_BOUNDARY")
    root = tmp_path / "attempts"
    root.mkdir()
    workspace = root / "worker"
    workspace.mkdir()
    sentinel = tmp_path / "unrelated.txt"
    sentinel.write_text("preserve")
    cancel = threading.Event()
    timer = threading.Timer(0.8, cancel.set)
    profile = SandboxProfile(uid=os.getuid(), gid=os.getgid(), wall_seconds=15)
    code = "import os,time; " + ("os.close(1); os.close(2); " if close_output else "") + "time.sleep(60)"
    timer.start()
    started = time.monotonic()
    try:
        receipt = DockerSandbox(root).run(
            workspace,
            ("/usr/local/bin/python", "-c", code),
            profile,
            cancel=cancel,
        )
    finally:
        timer.cancel()
        timer.join()
    assert receipt.reason == "cancelled" and receipt.exit_code is not None
    assert time.monotonic() - started < 5
    assert subprocess.run(["docker", "inspect", receipt.container_id], capture_output=True).returncode != 0
    assert sentinel.read_text() == "preserve"
    record_property("profile_sha256", receipt.profile_sha256)
    record_property("effective_config_sha256", receipt.effective_config_sha256)


@pytest.mark.docker_boundary
@pytest.mark.live
def test_closed_output_still_enforces_wall_time(tmp_path: Path) -> None:
    root = tmp_path / "attempts"
    root.mkdir()
    workspace = root / "worker"
    workspace.mkdir()
    profile = SandboxProfile(uid=os.getuid(), gid=os.getgid(), wall_seconds=0.5)
    receipt = DockerSandbox(root).run(
        workspace,
        ("/usr/local/bin/python", "-c", "import os,time;os.close(1);os.close(2);time.sleep(60)"),
        profile,
    )
    assert receipt.reason == "deadline_exceeded" and receipt.elapsed_seconds < 5
    assert subprocess.run(["docker", "inspect", receipt.container_id], capture_output=True).returncode != 0


@pytest.mark.docker_boundary
@pytest.mark.live
def test_cancel_after_container_creation_never_starts_the_worker(tmp_path: Path) -> None:
    root = tmp_path / "attempts"
    root.mkdir()
    workspace = root / "worker"
    workspace.mkdir()
    cancel = threading.Event()

    class CancelOnInspection(DockerSandbox):
        def _validate_effective(self, *args: object) -> None:
            super()._validate_effective(*args)  # type: ignore[arg-type]
            cancel.set()

    receipt = CancelOnInspection(root).run(
        workspace,
        ("/usr/local/bin/python", "-c", "open('/workspace/must-not-exist','w').write('bad')"),
        SandboxProfile(uid=os.getuid(), gid=os.getgid()),
        cancel=cancel,
    )
    assert receipt.reason == "cancelled" and receipt.exit_code is None
    assert not (workspace / "must-not-exist").exists()
    assert subprocess.run(["docker", "inspect", receipt.container_id], capture_output=True).returncode != 0
