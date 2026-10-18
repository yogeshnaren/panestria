"""Profile compatibility and real OS-pipe pressure, without Docker authority."""

import subprocess
import sys
import threading
import time
from dataclasses import replace

import pytest

from panestria.sandbox.native_tool_input import MAX_FRAME_BYTES
from panestria.sandbox.profiles import SandboxProfile, SandboxRejected
from panestria.sandbox.runner import DockerSandbox


def test_partial_selector_setup_failure_closes_actual_attach_pipes_and_process(tmp_path, monkeypatch):
    import selectors

    real_popen, real_selector = subprocess.Popen, selectors.DefaultSelector
    children = []

    def attach(*args, **kwargs):
        child = real_popen(
            [sys.executable, "-I", "-c", "import time;time.sleep(60)"],
            stdin=kwargs["stdin"],
            stdout=kwargs["stdout"],
            stderr=kwargs["stderr"],
        )
        children.append(child)
        return child

    def broken_selector():
        value = real_selector()
        register = value.register

        def fail_input(fileobj, events, data=None):
            if data == "input":
                raise OSError("synthetic_registration_failure")
            return register(fileobj, events, data)

        value.register = fail_input
        return value

    monkeypatch.setattr("panestria.sandbox.runner.subprocess.Popen", attach)
    monkeypatch.setattr("panestria.sandbox.runner.selectors.DefaultSelector", broken_selector)
    with pytest.raises(OSError, match="synthetic_registration_failure"):
        DockerSandbox(tmp_path)._execute(
            "ab" * 32, SandboxProfile(stdin_mode="native-frame-v1"), "cd" * 32, input_frame=b"x"
        )
    assert len(children) == 1 and children[0].poll() is not None
    assert children[0].stdin.closed and children[0].stdout.closed


@pytest.mark.parametrize(
    "name,expected",
    [
        ("mock-no-network", "af851a4e6f1930ff1c5a63bd7e3bc1a95af649f9697e2579890ce6a08812c2f7"),
        ("read-only-research", "c7d50dec5f0c61ed6a9b98c7bf4a731bec98c6402d3a82592e511ce3d6a2a4f5"),
        ("scoped-code-edit", "19d9aa4d5afcae01b7fa66179cc4636e2587742b75734bb15007354ef443c6eb"),
        ("restricted-offline", "7ff9fd4459bf727c03bfc0f54509b530d5d4e8e0bb8c37660bb1b9e036e2545d"),
    ],
)
def test_closed_stdin_hash_matches_actual_main_before_input_field(name, expected):
    # Recorded from a65400c5c5d4164f9994e02cd28c58583ea3723f, not recalculated
    # from today's serializer. Existing certificates must keep their identities.
    profile = SandboxProfile(name=name)
    assert profile.sha256() == expected
    framed = replace(profile, stdin_mode="native-frame-v1")
    framed.validate()
    assert framed.sha256() != expected


@pytest.mark.parametrize("mode", [None, True, "open", "native-frame-v2", []])
def test_unknown_input_modes_reject(mode):
    with pytest.raises(SandboxRejected, match="unknown_stdin_mode"):
        SandboxProfile(stdin_mode=mode).validate()


@pytest.mark.parametrize(
    "mode,data",
    [
        ("closed", b"x"),
        ("closed", b""),
        ("native-frame-v1", None),
        ("native-frame-v1", b""),
        ("native-frame-v1", "text"),
        ("native-frame-v1", bytearray(b"x")),
        ("native-frame-v1", b"x" * (MAX_FRAME_BYTES + 1)),
    ],
)
def test_input_contract_denies_before_docker_or_launch_intent(tmp_path, monkeypatch, mode, data):
    runner = DockerSandbox(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("no Docker or launch-intent side effect allowed")

    monkeypatch.setattr(runner, "_docker", forbidden)
    with pytest.raises(SandboxRejected, match="sandbox_input_binding_mismatch"):
        runner.run(
            tmp_path / "not-created", ("/usr/local/bin/python",), SandboxProfile(stdin_mode=mode), input_frame=data
        )


@pytest.mark.parametrize(
    "case,expected",
    [
        ("blocked-closed-output", "deadline_exceeded"),
        ("blocked-cancel", "cancelled"),
        ("early-input-close", "input_incomplete"),
        ("duplex-pressure", "completed"),
    ],
)
def test_actual_small_os_pipes_do_not_require_a_writer_thread(tmp_path, monkeypatch, case, expected):
    # Only the attach process/state seam is substituted. Actual child, 4096-byte
    # pipes, select/write/read, pressure, EOF and termination are exercised.
    real_popen = subprocess.Popen
    children = []
    programs = {
        "blocked-closed-output": "import os,time;os.close(1);os.close(2);time.sleep(60)",
        "blocked-cancel": "import time;time.sleep(60)",
        "early-input-close": "import os,time;os.close(0);time.sleep(.5)",
        "duplex-pressure": "import os,sys;os.write(1,b'p'*8192);data=sys.stdin.buffer.read();"
        "os.write(1,str(len(data)).encode())",
    }

    def attach(*args, **kwargs):
        assert kwargs["stdin"] == subprocess.PIPE
        child = real_popen(
            [sys.executable, "-I", "-c", programs[case]],
            stdin=kwargs["stdin"],
            stdout=kwargs["stdout"],
            stderr=kwargs["stderr"],
            pipesize=4096,
        )
        children.append(child)
        return child

    class PipeState(DockerSandbox):
        def _inspect(self, identity):
            code = children[0].poll()
            return {"State": {"Running": code is None, "ExitCode": code or 0, "OOMKilled": False}}

        def _docker(self, args, **kwargs):
            assert args == ["kill", "ab" * 32]
            children[0].kill()
            children[0].wait(timeout=3)
            return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr("panestria.sandbox.runner.subprocess.Popen", attach)
    cancel = threading.Event()
    timer = threading.Timer(0.2, cancel.set) if case == "blocked-cancel" else None
    if timer:
        timer.start()
    started = time.monotonic()
    threads = {t.ident for t in threading.enumerate()}
    try:
        receipt = PipeState(tmp_path)._execute(
            "ab" * 32,
            SandboxProfile(stdin_mode="native-frame-v1", wall_seconds=0.5, output_bytes=16384),
            "cd" * 32,
            cancel=cancel,
            input_frame=b"x" * MAX_FRAME_BYTES,
        )
        assert receipt.reason == expected and time.monotonic() - started < 3
        if case == "duplex-pressure":
            assert receipt.output == b"p" * 8192 + str(MAX_FRAME_BYTES).encode()
        assert children[0].poll() is not None
        assert children[0].stdin.closed and children[0].stdout.closed
        assert {t.ident for t in threading.enumerate()} <= threads
    finally:
        if timer:
            timer.cancel()
            timer.join()
        for child in children:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=3)
