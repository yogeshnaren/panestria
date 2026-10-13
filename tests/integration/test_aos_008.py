"""OS boundary tests use real pinned Docker containers; no mocked enforcement."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from panestria.sandbox.profiles import SandboxProfile, SandboxRejected
from panestria.sandbox.runner import DockerSandbox


@pytest.mark.parametrize(
    "changes",
    [
        dict(image="python:latest"),
        dict(uid=0),
        dict(pids=1),
        dict(memory_bytes=1),
        dict(wall_seconds=0),
        dict(output_bytes=0),
    ],
)
def test_profiles_fail_closed(changes: dict[str, object]) -> None:
    with pytest.raises(SandboxRejected):
        replace(SandboxProfile(), **changes).validate()


def test_workspace_scope_and_executable(tmp_path: Path, record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-008-TC01")
    root = tmp_path / "attempts"
    root.mkdir()
    runner = DockerSandbox(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(SandboxRejected, match="workspace_scope_denied"):
        runner.run(outside, ("/usr/local/bin/python", "-c", "pass"), SandboxProfile())
    link = root / "link"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(SandboxRejected, match="invalid_workspace"):
        runner.run(link, ("/usr/local/bin/python", "-c", "pass"), SandboxProfile())
    worker = root / "worker"
    worker.mkdir()
    with pytest.raises(SandboxRejected, match="unregistered_executable"):
        runner.run(worker, ("docker", "run", "--privileged"), SandboxProfile())


@pytest.mark.live
def test_os_effective_uid_mounts_egress_and_limits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, record_property: pytest.RecordProperty
) -> None:
    record_property("gate_case_id", "AOS-008-TC03")
    record_property("execution_mode", "OS_BOUNDARY")
    record_property("source_clauses", "AOS-008-F01,AOS-008-F02,AOS-008-AC01,AOS-008-AC02")
    root = tmp_path / "attempts"
    root.mkdir()
    worker = root / "worker"
    worker.mkdir()
    profile = SandboxProfile(uid=os.getuid(), gid=os.getgid(), wall_seconds=20)
    runner = DockerSandbox(root)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-sentinel-never-pass-to-workers")
    monkeypatch.setenv("PANESTRIA_DATABASE_URL", "synthetic-secret-dsn-never-pass")
    program = r"""
import json, os, socket
from pathlib import Path
checks = {"uid": os.geteuid(), "host_secrets_absent":
          "OPENAI_API_KEY" not in os.environ and "PANESTRIA_DATABASE_URL" not in os.environ}
try: Path('/etc/forbidden').write_text('bad'); checks['root_readonly'] = False
except OSError: checks['root_readonly'] = True
try: socket.create_connection(('1.1.1.1',443),timeout=1); checks['egress_denied'] = False
except OSError: checks['egress_denied'] = True
try: socket.getaddrinfo('example.com',443); checks['public_dns_denied'] = False
except OSError: checks['public_dns_denied'] = True
Path('/workspace/output.txt').write_text('bounded result')
status=Path('/proc/self/status').read_text()
checks['seccomp'] = next(line.split()[1] for line in status.splitlines() if line.startswith('Seccomp:'))
checks['caps'] = next(line.split()[1] for line in status.splitlines() if line.startswith('CapEff:'))
checks['nnp'] = next(line.split()[1] for line in status.splitlines() if line.startswith('NoNewPrivs:'))
checks['memory_max'] = Path('/sys/fs/cgroup/memory.max').read_text().strip()
checks['pids_max'] = Path('/sys/fs/cgroup/pids.max').read_text().strip()
checks['cpu_max'] = Path('/sys/fs/cgroup/cpu.max').read_text().strip()
checks['docker_socket_absent'] = not Path('/var/run/docker.sock').exists()
for family in [socket.AF_INET,socket.AF_INET6]:
 try: socket.socket(family,socket.SOCK_STREAM); checks[str(family)] = False
 except OSError: checks[str(family)] = True
print(json.dumps(checks))
"""
    receipt = runner.run(worker, ("/usr/local/bin/python", "-u", "-c", program), profile)
    assert receipt.exit_code == 0 and receipt.reason == "completed", receipt.output
    checks = json.loads(receipt.output)
    assert checks["uid"] == os.getuid() != 0
    assert checks["2"] is True and checks["10"] is True
    assert all(
        checks[key] is True
        for key in [
            "host_secrets_absent",
            "root_readonly",
            "egress_denied",
            "public_dns_denied",
            "docker_socket_absent",
        ]
    )
    assert checks["seccomp"] == "2" and int(checks["caps"], 16) == 0 and checks["nnp"] == "1"
    assert checks["memory_max"] == str(profile.memory_bytes) and checks["pids_max"] == str(profile.pids)
    quota, period = map(int, checks["cpu_max"].split())
    assert quota / period == profile.cpu_nanos / 1_000_000_000
    assert (worker / "output.txt").read_text() == "bounded result"
    assert subprocess.run(["docker", "inspect", receipt.container_id], capture_output=True).returncode != 0
    record_property("profile_sha256", receipt.profile_sha256)
    record_property("effective_config_sha256", receipt.effective_config_sha256)


@pytest.mark.live
@pytest.mark.parametrize(
    "pressure,expected",
    [("memory", "memory_limit"), ("output", "output_limit"), ("time", "deadline_exceeded"), ("pids", "completed")],
)
def test_resource_pressure_is_contained(
    tmp_path: Path, pressure: str, expected: str, record_property: pytest.RecordProperty
) -> None:
    record_property("gate_case_id", "AOS-008-TC03")
    record_property("execution_mode", "OS_BOUNDARY")
    root = tmp_path / "attempts"
    root.mkdir()
    worker = root / "worker"
    worker.mkdir()
    profile = SandboxProfile(
        uid=os.getuid(),
        gid=os.getgid(),
        memory_bytes=128 * 1024**2,
        wall_seconds=2 if pressure == "time" else 20,
        output_bytes=2048,
    )
    programs = {
        "memory": "x=bytearray(384*1024*1024)",
        "output": "import os; os.write(1,b'x'*100000)",
        "time": "import time; time.sleep(60)",
        "pids": """import subprocess
children=[]
try:
 for _ in range(100): children.append(subprocess.Popen(['/usr/local/bin/python','-c','import time;time.sleep(10)']))
except OSError: print('pids-bounded',len(children))
finally:
 for child in children: child.terminate()
 for child in children: child.wait()
""",
    }
    receipt = DockerSandbox(root).run(worker, ("/usr/local/bin/python", "-u", "-c", programs[pressure]), profile)
    assert receipt.reason == expected, receipt
    assert len(receipt.output) <= profile.output_bytes and receipt.elapsed_seconds < profile.wall_seconds + 10
    if pressure == "pids":
        assert b"pids-bounded" in receipt.output
    assert subprocess.run(["docker", "inspect", receipt.container_id], capture_output=True).returncode != 0


def test_mount_symlink_proc_escape(tmp_path: Path, record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-008-TC01")
    root = tmp_path / "attempts"
    root.mkdir()
    worker = root / "worker"
    worker.mkdir()
    private = tmp_path / "private"
    private.write_text("synthetic sentinel")
    runner = DockerSandbox(root)
    link = worker / "escape"
    link.symlink_to(private)
    with pytest.raises(SandboxRejected, match="workspace_link_escape"):
        runner.run(worker, ("/usr/local/bin/python", "-c", "pass"), SandboxProfile())
    link.unlink()
    os.link(private, link)
    with pytest.raises(SandboxRejected, match="workspace_hardlink_denied"):
        runner.run(worker, ("/usr/local/bin/python", "-c", "pass"), SandboxProfile())
    link.unlink()
    (worker / ".env.local").write_text("synthetic sentinel")
    with pytest.raises(SandboxRejected, match="private_workspace_path"):
        runner.run(worker, ("/usr/local/bin/python", "-c", "pass"), SandboxProfile())


@pytest.mark.live
def test_readonly_profile_and_private_paths(tmp_path: Path, record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-008-TC01")
    record_property("execution_mode", "OS_BOUNDARY")
    root = tmp_path / "attempts"
    root.mkdir()
    worker = root / "worker"
    worker.mkdir()
    program = r"""
from pathlib import Path
for path in ['/etc/shadow','/home/yogesh/.ssh/id_rsa','/proc/1/root/home/yogesh/.ssh/id_rsa','/parent/sentinel']:
 try: Path(path).read_bytes(); raise AssertionError('private path readable')
 except OSError: pass
try: Path('/workspace/forbidden').write_text('bad'); raise AssertionError('readonly workspace writable')
except OSError: pass
print('private-paths-denied')
"""
    profile = SandboxProfile(name="restricted-offline", uid=os.getuid(), gid=os.getgid())
    receipt = DockerSandbox(root).run(worker, ("/usr/local/bin/python", "-c", program), profile)
    assert receipt.exit_code == 0 and b"private-paths-denied" in receipt.output
    assert not (worker / "forbidden").exists()


@pytest.mark.live
def test_sandbox_failure_cleanup(tmp_path: Path, record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-008-TC04")
    record_property("execution_mode", "OS_BOUNDARY")
    root = tmp_path / "attempts"
    root.mkdir()
    worker = root / "worker"
    worker.mkdir()
    sentinel = tmp_path / "unrelated"
    sentinel.write_text("keep")

    class RejectedSandbox(DockerSandbox):
        def _validate_effective(self, *args: object) -> None:
            raise SandboxRejected("effective_profile_mismatch")

    identity = "00000000-0000-4000-8000-000000000088"
    with pytest.raises(SandboxRejected, match="effective_profile_mismatch"):
        RejectedSandbox(root).run(
            worker,
            ("/usr/local/bin/python", "-c", "open('/workspace/marker','w').write('bad')"),
            SandboxProfile(uid=os.getuid(), gid=os.getgid()),
            attempt_id=identity,
        )
    assert not (worker / "marker").exists() and sentinel.read_text() == "keep"
    assert (
        subprocess.run(
            ["docker", "inspect", "panestria-worker-" + identity.replace("-", "")], capture_output=True
        ).returncode
        != 0
    )


def test_network_gateway_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, record_property: pytest.RecordProperty
) -> None:
    import socket

    from panestria.sandbox.egress import EgressDenied, EgressGateway, resolve_destination

    record_property("gate_case_id", "AOS-008-TC02")
    record_property("source_clauses", "AOS-008-F02,AOS-008-F03,AOS-008-AC02")
    allowed = frozenset({"api.anthropic.com"})
    for authority in [
        "127.0.0.1:443",
        "169.254.169.254:443",
        "[::1]:443",
        "evil.example:443",
        "api.anthropic.com:80",
        "api.anthropic.com.evil:443",
        "user@api.anthropic.com:443",
    ]:
        with pytest.raises(EgressDenied, match="destination_denied"):
            resolve_destination(authority, allowed)
    for private in ["127.0.0.1", "169.254.169.254", "10.0.0.1", "100.64.0.1", "::1", "::ffff:127.0.0.1"]:
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda *args, value=private, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (value, 443))],
        )
        with pytest.raises(EgressDenied, match="private_destination_denied"):
            resolve_destination("api.anthropic.com:443", allowed)
    calls = []

    def public(host: str, port: int, **kwargs: object) -> object:
        calls.append(host)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("104.18.0.1", port))]

    monkeypatch.setattr(socket, "getaddrinfo", public)
    assert resolve_destination("api.anthropic.com:443", allowed) == ("104.18.0.1", 443)
    assert calls == ["api.anthropic.com"]
    with EgressGateway(tmp_path / "gateway", allowed) as gateway:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.connect(str(gateway.path))
            connection.sendall(b"CONNECT 169.254.169.254:443 HTTP/1.1\r\n\r\n")
            assert connection.recv(256).startswith(b"HTTP/1.1 403")
        assert all(entry[1] == "DENIED" for entry in gateway.server.audit)
    assert not (tmp_path / "gateway").exists()


@pytest.mark.live
def test_provider_gateway_live_tls(tmp_path: Path, record_property: pytest.RecordProperty) -> None:
    import socket
    import ssl

    from panestria.sandbox.egress import EgressGateway

    record_property("gate_case_id", "AOS-008-TC02")
    record_property("execution_mode", "OS_BOUNDARY")
    # No auth or model request: prove the allowlisted TLS channel itself.
    with EgressGateway(tmp_path / "gateway", frozenset({"api.anthropic.com"})) as gateway:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(10)
            connection.connect(str(gateway.path))
            connection.sendall(b"CONNECT api.anthropic.com:443 HTTP/1.1\r\n\r\n")
            header = bytearray()
            while not header.endswith(b"\r\n\r\n"):
                header.extend(connection.recv(1))
            assert header.startswith(b"HTTP/1.1 200")
            with ssl.create_default_context().wrap_socket(connection, server_hostname="api.anthropic.com") as secure:
                secure.sendall(b"HEAD / HTTP/1.1\r\nHost: api.anthropic.com\r\nConnection: close\r\n\r\n")
                assert secure.recv(1024).startswith(b"HTTP/1.1 ")
        assert ("api.anthropic.com:443", "ALLOWED") in gateway.server.audit
