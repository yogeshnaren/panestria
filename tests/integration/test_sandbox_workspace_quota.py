"""SEC-M1: a writable workspace cannot grow past its profile quota."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from panestria.sandbox.profiles import SandboxProfile
from panestria.sandbox.runner import DockerSandbox, workspace_usage

QUOTA = 4 * 1024**2


def _worker(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "attempts"
    worker = root / "worker"
    worker.mkdir(parents=True)
    return root, worker


def _profile() -> SandboxProfile:
    return SandboxProfile(uid=os.getuid(), gid=os.getgid(), wall_seconds=30, workspace_bytes=QUOTA)


@pytest.mark.docker_boundary
def test_sec_m1_many_file_writer_is_stopped(tmp_path: Path) -> None:
    root, worker = _worker(tmp_path)
    program = """import itertools
for index in itertools.count():
    with open(f'/workspace/fill-{index}', 'wb') as stream:
        stream.write(b'x' * 262144)
"""
    receipt = DockerSandbox(root).run(worker, ("/usr/local/bin/python", "-u", "-c", program), _profile())
    assert receipt.reason == "workspace_quota_exceeded", receipt
    assert receipt.elapsed_seconds < 25
    # Overshoot is bounded by writer throughput over one scan interval.
    usage = workspace_usage(worker)
    assert usage is not None and QUOTA < usage < 64 * QUOTA
    assert subprocess.run(["docker", "inspect", receipt.container_id], capture_output=True).returncode != 0


@pytest.mark.docker_boundary
def test_sec_m1_single_file_is_capped_by_the_size_limit(tmp_path: Path) -> None:
    root, worker = _worker(tmp_path)
    program = """import errno
try:
    with open('/workspace/big', 'wb') as stream:
        for _ in range(64):
            stream.write(b'x' * 262144)
            stream.flush()
except OSError as exc:
    print('blocked', exc.errno == errno.EFBIG)
"""
    receipt = DockerSandbox(root).run(worker, ("/usr/local/bin/python", "-u", "-c", program), _profile())
    assert b"blocked True" in receipt.output, receipt
    assert (worker / "big").stat().st_size <= QUOTA
    assert receipt.reason == "completed"


@pytest.mark.docker_boundary
def test_sec_m1_writes_within_quota_complete(tmp_path: Path) -> None:
    root, worker = _worker(tmp_path)
    program = "open('/workspace/small', 'wb').write(b'x' * 1024)"
    receipt = DockerSandbox(root).run(worker, ("/usr/local/bin/python", "-c", program), _profile())
    assert receipt.reason == "completed" and receipt.exit_code == 0, receipt
    assert (worker / "small").stat().st_size == 1024
