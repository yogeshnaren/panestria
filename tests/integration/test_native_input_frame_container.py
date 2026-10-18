"""Actual fixed parser-only containers, not production launcher conformance."""

import hashlib
import json
import os
import re
import struct
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from panestria.sandbox import native_tool_input

IMAGE = "python@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9"
PURPOSE = "bounded-native-input-parser"
PROGRAM = """
import hashlib,json,sys
sys.path.insert(0, '/runtime')
from native_tool_input import InputFrameRejected,decode_frame
try:
    frame=decode_frame(sys.stdin.buffer,script_sha256=sys.argv[1],request_sha256=sys.argv[2])
except InputFrameRejected:
    print(json.dumps({'status':'rejected'}))
    sys.exit(2)
print(json.dumps({'status':'parsed','script_bytes':len(frame.script),'request_bytes':len(frame.request),
                  'script_sha256':hashlib.sha256(frame.script).hexdigest(),
                  'request_sha256':hashlib.sha256(frame.request).hexdigest()}))
"""


def command(*args, timeout=20):
    return subprocess.run(["docker", *args], check=True, capture_output=True, timeout=timeout)


def inspect(ref):
    return json.loads(command("inspect", ref).stdout)[0]


@pytest.mark.parametrize("case", ["maximum", "truncated", "trailing", "version", "length", "digest"])
def test_actual_fixed_container_frame(case):
    # Padded inert bytes are never compiled, executed, or parsed as JSON.
    script = b"raise RuntimeError('MUST_NOT_EXECUTE')\n".ljust(native_tool_input.MAX_SCRIPT_BYTES, b" ")
    body = b"PUBLIC_SYNTHETIC_NOT_JSON".ljust(native_tool_input.MAX_REQUEST_BYTES, b" ")
    data = native_tool_input.encode_frame(script, body)
    script_hash = hashlib.sha256(script).hexdigest()
    body_hash = hashlib.sha256(body).hexdigest()
    if case == "truncated":
        data = data[:-1]
    elif case == "trailing":
        data += b"x"
    elif case == "version":
        data = b"PANESTRIA-TOOL-2\n" + data[len(native_tool_input.MAGIC) :]
    elif case == "length":
        data = native_tool_input.MAGIC + struct.pack(">II", 0xFFFFFFFF, 1)
    elif case == "digest":
        script_hash = "0" * 64
    # No image pulls, credentials, vendor CLI, database or provider calls.
    command("image", "inspect", IMAGE)
    name = "panestria-input-frame-" + uuid4().hex
    source = Path(native_tool_input.__file__).resolve()
    cid = None
    attach = None
    try:
        cid = (
            command(
                "create",
                "--pull",
                "never",
                "--name",
                name,
                "--label",
                "panestria.purpose=" + PURPOSE,
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                "--pids-limit",
                "16",
                "--memory",
                "64m",
                "--cpus",
                "0.25",
                "--ulimit",
                "core=0",
                "--interactive",
                "--attach",
                "stdin",
                "--attach",
                "stdout",
                "--attach",
                "stderr",
                "--mount",
                f"type=bind,src={source},dst=/runtime/native_tool_input.py,readonly",
                IMAGE,
                "/usr/local/bin/python",
                "-I",
                "-B",
                "-c",
                PROGRAM,
                script_hash,
                body_hash,
            )
            .stdout.decode()
            .strip()
        )
        assert re.fullmatch(r"[0-9a-f]{64}", cid)
        actual = inspect(cid)
        config, host = actual["Config"], actual["HostConfig"]
        assert actual["Id"] == cid and actual["Name"] == "/" + name
        assert config["Labels"]["panestria.purpose"] == PURPOSE
        assert config["User"] == f"{os.getuid()}:{os.getgid()}" and os.getuid() != 0
        assert config["OpenStdin"] and config["AttachStdin"] and config["StdinOnce"]
        assert not config["Tty"] and host["NetworkMode"] == "none" and host["ReadonlyRootfs"]
        assert host["CapDrop"] == ["ALL"] and "no-new-privileges" in host["SecurityOpt"]
        assert host["PidsLimit"] == 16 and host["Memory"] == 64 * 1024 * 1024
        assert host["NanoCpus"] == 250_000_000
        assert {item["Name"]: (item["Soft"], item["Hard"]) for item in host["Ulimits"]}["core"] == (0, 0)
        assert [(item["Source"], item["Destination"], item["RW"]) for item in actual["Mounts"]] == [
            (str(source), "/runtime/native_tool_input.py", False)
        ]
        attach = subprocess.Popen(
            ["docker", "start", "--attach", "--interactive", cid],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        output, error = attach.communicate(data, timeout=15)
        assert not error and len(output) < 1024
        expected_code = 0 if case == "maximum" else 2
        assert attach.returncode == expected_code
        if case == "maximum":
            assert json.loads(output) == {
                "status": "parsed",
                "script_bytes": len(script),
                "request_bytes": len(body),
                "script_sha256": script_hash,
                "request_sha256": body_hash,
            }
        else:
            assert json.loads(output) == {"status": "rejected"}
        stopped = inspect(cid)["State"]
        assert not stopped["Running"] and not stopped["OOMKilled"] and stopped["ExitCode"] == expected_code
    finally:
        if attach is not None and attach.poll() is None:
            attach.kill()
            attach.wait(timeout=5)
        # Even a lost create reply can only clean this exact randomly named,
        # purpose-bound fixture. Never scan, prune, or remove unrelated resources.
        probe = subprocess.run(["docker", "inspect", cid or name], capture_output=True, timeout=20)
        if probe.returncode == 0:
            owned = json.loads(probe.stdout)[0]
            assert owned["Name"] == "/" + name and owned["Config"]["Labels"]["panestria.purpose"] == PURPOSE
            if cid is not None:
                assert owned["Id"] == cid
            command("rm", "--force", "--volumes", owned["Id"])
            absent = subprocess.run(["docker", "inspect", owned["Id"]], capture_output=True, timeout=20)
            assert absent.returncode != 0
