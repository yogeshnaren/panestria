"""Owned synthetic socket/container fixtures, never a native auth or release certificate."""

import hashlib
import json
import os
import selectors
import socketserver
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from panestria.sandbox.profiles import DEFAULT_IMAGE

PROGRAM = Path(__file__).resolve().parents[1] / "src/panestria/sandbox/native_proxy_relay.py"


class _Echo(socketserver.BaseRequestHandler):
    def handle(self):
        self.server.accepted += 1
        self.request.settimeout(3)
        body = bytearray()
        try:
            while len(body) <= 512 * 1024:
                data = self.request.recv(16384)
                if not data:
                    self.request.sendall(body)
                    return
                body.extend(data)
        except OSError:
            pass


class _PrivateEcho(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    block_on_close = False
    accepted = 0

    def handle_error(self, request, client_address):
        pass


@contextmanager
def echo_gateway(directory):
    directory.mkdir(mode=0o700)
    path = directory / "connect.sock"
    server = _PrivateEcho(str(path), _Echo)
    path.chmod(0o600)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.05), daemon=True)
    thread.start()
    try:
        yield path, server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        path.unlink(missing_ok=True)


def docker(*args, timeout=20):
    result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)
    assert result.returncode == 0, "owned_native_relay_container_operation_failed"
    return result.stdout


@contextmanager
def relay_container(endpoint):
    identity = uuid4().hex
    info = endpoint.stat()
    before = hashlib.sha256(PROGRAM.read_bytes()).hexdigest()
    image = json.loads(docker("image", "inspect", DEFAULT_IMAGE))[0]
    uid, gid = os.getuid(), os.getgid()
    assert uid != 0 and gid != 0, "nonroot_native_relay_backend_required"
    args = [
        "create",
        "--name",
        "panestria-native-relay-test-" + identity,
        "--label",
        "panestria.purpose=native-relay-test",
        "--label",
        "panestria.relay_test=" + identity,
        "--pull",
        "never",
        "--network",
        "none",
        "--user",
        f"{uid}:{gid}",
        "--read-only",
        "--log-driver",
        "none",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges=true",
        "--memory",
        "134217728",
        "--memory-swap",
        "134217728",
        "--cpus",
        "0.5",
        "--pids-limit",
        "32",
        "--ulimit",
        "core=0:0",
        "--ulimit",
        "nofile=64:64",
        "--init",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=16m,mode=1777",
        "--workdir",
        "/tmp",
        "--env",
        "HOME=/tmp/isolated-home",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        "--env",
        "PYTHONNOUSERSITE=1",
        "--mount",
        f"type=bind,src={endpoint.parent},dst=/gateway,readonly",
        "--mount",
        f"type=bind,src={PROGRAM},dst=/runtime/native_proxy_relay.py,readonly",
        "--entrypoint",
        "/usr/local/bin/python",
        DEFAULT_IMAGE,
        "-I",
        "/runtime/native_proxy_relay.py",
        str(info.st_dev),
        str(info.st_ino),
    ]
    identifier = docker(*args).strip()
    assert len(identifier) == 64 and all(c in "0123456789abcdef" for c in identifier)
    process = None
    try:
        actual = json.loads(docker("inspect", identifier))[0]
        host, config = actual["HostConfig"], actual["Config"]
        assert actual["Image"] == image["Id"] and config["User"] == f"{uid}:{gid}"
        assert host["NetworkMode"] == "none" and host["ReadonlyRootfs"] and not host["Privileged"]
        assert not host["PortBindings"] and host["LogConfig"]["Type"] == "none"
        assert host["Memory"] == host["MemorySwap"] == 128 * 1024 * 1024
        assert host["NanoCpus"] == 500_000_000 and host["PidsLimit"] == 32
        assert host["CapDrop"] == ["ALL"] and "no-new-privileges=true" in host["SecurityOpt"]
        assert {(m["Destination"], m["Source"], m["RW"]) for m in actual["Mounts"]} == {
            ("/gateway", str(endpoint.parent), False),
            ("/runtime/native_proxy_relay.py", str(PROGRAM), False),
        }
        assert not any(
            value.startswith(("ANTHROPIC_", "OPENAI_", "CLAUDE_", "PANESTRIA_DATABASE_URL=", "DBUS_"))
            for value in config["Env"]
        )
        process = subprocess.Popen(
            ["docker", "start", "--attach", identifier], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        assert process.stdout is not None and process.stderr is not None
        deadline = time.monotonic() + 10
        output = bytearray()
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while bytes(output) != b"NATIVE_PROXY_READY\n":
                assert time.monotonic() < deadline and len(output) < 1024, "native_relay_startup_unconfirmed"
                for key, _ in selector.select(0.05):
                    data = os.read(key.fd, 1024)
                    assert data, "native_relay_startup_failed"
                    output.extend(data)
        yield identifier, actual
    finally:
        current = json.loads(docker("inspect", identifier))[0]
        assert current["Id"] == identifier and current["Config"]["Labels"]["panestria.relay_test"] == identity
        docker("rm", "--force", "--volumes", identifier)
        if process is not None:
            process.communicate(timeout=5)
        assert hashlib.sha256(PROGRAM.read_bytes()).hexdigest() == before


def client(identifier, program):
    return json.loads(docker("exec", identifier, "/usr/local/bin/python", "-I", "-c", program))
