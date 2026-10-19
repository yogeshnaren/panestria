"""Actual production DockerSandbox transport, with public fixed synthetic data."""

import hashlib
import json
import os
import subprocess
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

from panestria.sandbox import native_tool_input
from panestria.sandbox.profiles import ReadOnlyMount, SandboxProfile, SandboxRejected
from panestria.sandbox.runner import DockerSandbox


def setup(tmp_path, *, seconds=10):
    root = tmp_path / "attempts"
    workspace = root / "workspace"
    workspace.mkdir(parents=True)
    return (
        root,
        workspace,
        SandboxProfile(
            name="restricted-offline",
            uid=os.getuid(),
            gid=os.getgid(),
            stdin_mode="native-frame-v1",
            wall_seconds=seconds,
            memory_bytes=64 * 1024**2,
            output_bytes=4096,
        ),
    )


class Observed(DockerSandbox):
    def __init__(self, root, **kwargs):
        super().__init__(root, **kwargs)
        self.actual = None

    def _validate_effective(self, actual, *args):
        self.actual = actual
        return super()._validate_effective(actual, *args)


def removed(receipt):
    assert subprocess.run(["docker", "inspect", receipt.container_id], capture_output=True, timeout=10).returncode != 0


def test_actual_maximum_frame_eof_and_inherited_isolation(tmp_path):
    root, workspace, profile = setup(tmp_path)
    script = b"raise RuntimeError('DO_NOT_EXECUTE')".ljust(native_tool_input.MAX_SCRIPT_BYTES, b" ")
    body = b"PUBLIC_SYNTHETIC_NOT_JSON".ljust(native_tool_input.MAX_REQUEST_BYTES, b" ")
    sh, rh = hashlib.sha256(script).hexdigest(), hashlib.sha256(body).hexdigest()
    program = """
import hashlib,json,os,socket,sys
from pathlib import Path
sys.path.insert(0,'/runtime')
from native_tool_input import decode_frame
frame=decode_frame(sys.stdin.buffer,script_sha256=sys.argv[1],request_sha256=sys.argv[2])
denied=[]
for family in (socket.AF_INET,socket.AF_INET6):
 try: socket.socket(family);denied.append(False)
 except OSError: denied.append(True)
status=Path('/proc/self/status').read_text().splitlines()
prefixes=('Seccomp:','CapEff:','NoNewPrivs:')
controls={line.split(':')[0]:line.split()[1] for line in status if line.startswith(prefixes)}
print(json.dumps({'sizes':[len(frame.script),len(frame.request)],'hashes':[hashlib.sha256(frame.script).hexdigest(),
 hashlib.sha256(frame.request).hexdigest()],'uid':os.getuid(),'denied':denied,'controls':controls}))
"""
    runner = Observed(
        root,
        runtime_mounts=(ReadOnlyMount(Path(native_tool_input.__file__).resolve(), "/runtime/native_tool_input.py"),),
    )

    receipt = runner.run(
        workspace,
        ("/usr/local/bin/python", "-I", "-c", program, sh, rh),
        profile,
        input_frame=native_tool_input.encode_frame(script, body),
    )
    assert receipt.reason == "completed" and receipt.exit_code == 0
    observed = json.loads(receipt.output)
    assert observed == {
        "sizes": [len(script), len(body)],
        "hashes": [sh, rh],
        "uid": os.getuid(),
        "denied": [True, True],
        "controls": {"Seccomp": "2", "CapEff": "0000000000000000", "NoNewPrivs": "1"},
    }
    actual = runner.actual
    assert actual["Config"]["OpenStdin"] and actual["Config"]["AttachStdin"] and actual["Config"]["StdinOnce"]
    assert not actual["Config"]["Tty"]
    assert actual["HostConfig"]["Memory"] == profile.memory_bytes
    assert receipt.profile_sha256 == profile.sha256()
    assert "PUBLIC_SYNTHETIC_NOT_JSON" not in json.dumps(actual)
    assert list(workspace.iterdir()) == []
    removed(receipt)


@pytest.mark.parametrize("client_exit", [0, 42])
def test_failed_attach_cannot_report_an_unstarted_container_as_success(tmp_path, monkeypatch, client_exit):
    import sys

    root, workspace, profile = setup(tmp_path)
    real_popen = subprocess.Popen
    captured = []

    def fail_attach(args, **kwargs):
        if args[:3] == ["docker", "start", "--attach"]:
            captured.append(args[-1])
            # Explicitly injected attach-client failure. Actual Docker create,
            # inspection and exact cleanup still run; the worker never starts.
            return real_popen(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    f"import sys;sys.stdin.buffer.read();print('SYNTHETIC_HOST_DIAGNOSTIC');sys.exit({client_exit})",
                ],
                **kwargs,
            )
        return real_popen(args, **kwargs)

    monkeypatch.setattr("panestria.sandbox.runner.subprocess.Popen", fail_attach)
    receipt = DockerSandbox(root).run(
        workspace,
        ("/usr/local/bin/python", "-c", "raise AssertionError('must never start')"),
        profile,
        input_frame=b"x",
    )
    assert receipt.reason == "attachment_failed" and receipt.exit_code == 0
    assert receipt.output == b"" and captured == [receipt.container_id]
    removed(receipt)


def test_actual_default_profile_stdin_is_closed(tmp_path):
    root, workspace, framed = setup(tmp_path)
    runner = Observed(root)
    receipt = runner.run(
        workspace,
        ("/usr/local/bin/python", "-c", "import sys;print(len(sys.stdin.buffer.read()))"),
        replace(framed, stdin_mode="closed"),
    )
    assert receipt.reason == "completed" and receipt.output.strip() == b"0"
    assert all(runner.actual["Config"][k] is False for k in ("OpenStdin", "AttachStdin", "StdinOnce", "Tty"))
    removed(receipt)


@pytest.mark.parametrize(
    "case,expected",
    [
        ("blocked-reader", "deadline_exceeded"),
        ("closed-output", "deadline_exceeded"),
        ("output-pressure", "output_limit"),
        ("memory-pressure", "memory_limit"),
        ("early-exit", "failed"),
    ],
)
def test_actual_input_adverse_cases_terminate_and_remove(tmp_path, case, expected):
    root, workspace, profile = setup(tmp_path, seconds=1 if expected == "deadline_exceeded" else 10)
    programs = {
        "blocked-reader": "import time;time.sleep(60)",
        "closed-output": "import os,time;os.close(1);os.close(2);time.sleep(60)",
        "output-pressure": "import os,time;os.write(1,b'x'*1000000);time.sleep(60)",
        # Consume stdin first, then fault in small bounded allocations until the
        # actual 64MiB cgroup cap is hit. One huge malloc can instead be refused
        # by host overcommit policy with MemoryError before cgroup OOM is tested.
        "memory-pressure": (
            "import sys;sys.stdin.buffer.read();blocks=[]\n"
            "while True: blocks.append(bytearray(4*1024*1024))"
        ),
        "early-exit": "raise SystemExit(7)",
    }
    receipt = DockerSandbox(root).run(
        workspace,
        ("/usr/local/bin/python", "-u", "-c", programs[case]),
        profile,
        input_frame=b"x" * native_tool_input.MAX_FRAME_BYTES,
    )
    if expected == "failed":
        assert receipt.reason in ("process_failed", "input_incomplete")
    else:
        assert receipt.reason == expected, (receipt.reason, receipt.exit_code, receipt.oom_killed, receipt.output)
        if case == "memory-pressure":
            assert receipt.oom_killed is True
    assert len(receipt.output) <= profile.output_bytes and receipt.elapsed_seconds < profile.wall_seconds + 6
    assert receipt.exit_code is not None
    removed(receipt)


@pytest.mark.parametrize(
    "mode,tamper",
    [
        ("closed", "open"),
        ("native-frame-v1", "close"),
        ("native-frame-v1", "tty"),
        ("native-frame-v1", "no-stdout"),
        ("native-frame-v1", "no-stderr"),
    ],
)
def test_actual_docker_input_flags_must_match_approved_profile(tmp_path, mode, tamper):
    root, workspace, profile = setup(tmp_path)
    profile = replace(profile, stdin_mode=mode)
    created = []

    class Tampered(Observed):
        def _docker(self, args, **kwargs):
            if args[0] == "create":
                index = args.index(profile.image)
                if tamper == "open":
                    args = args[:index] + ["--interactive"] + args[index:]
                elif tamper == "close":
                    args = [v for v in args if v != "--interactive"]
                elif tamper.startswith("no-"):
                    stream = tamper.removeprefix("no-")
                    position = args.index(stream)
                    assert args[position - 1] == "--attach"
                    args = args[: position - 1] + args[position + 1 :]
                else:
                    args = args[:index] + ["--tty"] + args[index:]
            result = super()._docker(args, **kwargs)
            if args[0] == "create":
                created.append(result.stdout.strip())
            return result

    with pytest.raises(SandboxRejected, match="effective_profile_mismatch"):
        Tampered(root).run(
            workspace,
            ("/usr/local/bin/python", "-c", "open('/workspace/must-not-exist','w')"),
            profile,
            input_frame=b"x" if mode != "closed" else None,
        )
    assert not (workspace / "must-not-exist").exists() and len(created) == 1
    assert subprocess.run(["docker", "inspect", created[0]], capture_output=True, timeout=10).returncode != 0


def test_actual_blocked_input_cancels_after_observed_running_state(tmp_path):
    root, workspace, profile = setup(tmp_path, seconds=15)
    cancel = threading.Event()
    launch = []
    observed_running = threading.Event()
    finished = threading.Event()

    def watch():
        while not finished.wait(0.05):
            if not launch:
                continue
            result = subprocess.run(["docker", "inspect", launch[0].name], capture_output=True, timeout=3)
            if result.returncode != 0:
                continue
            actual = json.loads(result.stdout)[0]
            if actual["Config"]["Labels"]["panestria.launch"] == launch[0].launch_id and actual["State"]["Running"]:
                observed_running.set()
                cancel.set()
                return

    watcher = threading.Thread(target=watch)
    watcher.start()
    started = time.monotonic()
    try:
        receipt = DockerSandbox(root, on_launch=lambda ref, p: launch.append(ref)).run(
            workspace,
            ("/usr/local/bin/python", "-c", "import time;time.sleep(60)"),
            profile,
            cancel=cancel,
            input_frame=b"x" * native_tool_input.MAX_FRAME_BYTES,
        )
        assert observed_running.is_set() and receipt.reason == "cancelled"
        assert time.monotonic() - started < 8
        removed(receipt)
    finally:
        finished.set()
        watcher.join(timeout=5)
        assert not watcher.is_alive()


def test_killed_actual_attach_client_cannot_hide_running_worker(tmp_path, monkeypatch):
    root, workspace, profile = setup(tmp_path, seconds=15)
    real_popen = subprocess.Popen
    clients = []
    observed_running = threading.Event()
    finished = threading.Event()

    def attach(args, **kwargs):
        process = real_popen(args, **kwargs)
        if args[:3] == ["docker", "start", "--attach"]:
            clients.append((process, args[-1]))
        return process

    def watch():
        while not finished.wait(0.05):
            if not clients:
                continue
            client, cid = clients[0]
            result = subprocess.run(["docker", "inspect", cid], capture_output=True, timeout=3)
            if result.returncode == 0:
                actual = json.loads(result.stdout)[0]
                if actual["Id"] == cid and actual["State"]["Running"]:
                    observed_running.set()
                    client.kill()  # This fixture's attach client, not the controller or daemon.
                    return

    monkeypatch.setattr("panestria.sandbox.runner.subprocess.Popen", attach)
    watcher = threading.Thread(target=watch)
    watcher.start()
    started = time.monotonic()
    try:
        receipt = DockerSandbox(root).run(
            workspace,
            ("/usr/local/bin/python", "-c", "import time;time.sleep(60)"),
            profile,
            input_frame=b"x" * native_tool_input.MAX_FRAME_BYTES,
        )
        assert observed_running.is_set() and receipt.reason in ("attachment_failed", "input_incomplete")
        assert time.monotonic() - started < 8 and receipt.exit_code is not None
        removed(receipt)
    finally:
        finished.set()
        watcher.join(timeout=5)
        assert not watcher.is_alive()
