"""Synthetic native executable for OS tests, never evidence of actual Claude."""

import hashlib
import os
from pathlib import Path

from panestria.brokers.harness import native_bootstrap as bootstrap
from panestria.brokers.harness.cli_profile import BinaryPin


def synthetic_pin(tmp_path, monkeypatch, *, behavior="success"):
    sentinel = tmp_path / "unmounted-synthetic-secret"
    sentinel.write_text("SYNTHETIC_NOT_AN_OWNER_SECRET")
    script = tmp_path / "synthetic-native"
    script.write_text(
        "#!/usr/local/bin/python\n"
        "import os,socket,pathlib,sys,time,errno\n"
        "assert sys.argv[1:3]==['--safe-mode','--restricted']\n"
        "assert not pathlib.Path(" + repr(str(sentinel)) + ").exists()\n"
        "env_names=('ANTHROPIC_','OPENAI_','CLAUDE_','PANESTRIA_DATABASE_URL','DBUS_')\n"
        "assert not any(k.startswith(env_names) for k in os.environ)\n"
        "assert os.geteuid()!=0\n"
        "for family in (socket.AF_INET,socket.AF_INET6):\n"
        " try: socket.socket(family,socket.SOCK_STREAM)\n"
        " except OSError as exc: assert exc.errno==errno.EPERM\n"
        " else: raise AssertionError('internet_socket_escaped_seccomp')\n"
        "for name in ('/workspace/unexpected-write','/runtime/native','/runtime/panestria-no-network.py'):\n"
        " try: pathlib.Path(name).write_bytes(b'synthetic')\n"
        " except OSError: pass\n"
        " else: raise AssertionError('read_only_mount_escaped')\n"
        "status=pathlib.Path('/proc/self/status').read_text()\n"
        "caps=next(line.split()[1] for line in status.splitlines() if line.startswith('CapEff:'))\n"
        "assert caps=='0000000000000000'\n"
        "assert next(line.split()[1] for line in status.splitlines() if line.startswith('NoNewPrivs:'))=='1'\n"
        "assert next(line.split()[1] for line in status.splitlines() if line.startswith('Seccomp:'))=='2'\n"
        "assert pathlib.Path('/sys/fs/cgroup/memory.max').read_text().strip()=='536870912'\n"
        "behavior=" + repr(behavior) + "\n"
        "if behavior=='timeout':time.sleep(5)\n"
        "if behavior=='closed-output':os.close(1);os.close(2);time.sleep(5)\n"
        "if behavior=='pressure':os.write(1,b'x'*262144);time.sleep(5)\n"
        "if behavior=='fail':sys.exit(7)\n"
        "if behavior=='invalid-utf8':os.write(1,b'\\xff');sys.exit(0)\n"
        "if sys.argv[-1]=='--version':\n"
        " print('0.0.0' if behavior=='wrong-version' else '2.1.273 (Claude Code)')\n"
        "elif sys.argv[-1]=='--help':\n"
        " print('--help' if behavior=='missing-controls' else "
        + repr(" ".join(sorted(bootstrap.VISIBLE_CONTROLS)))
        + ")\n"
        "else:raise AssertionError('unexpected_native_command')\n"
    )
    script.chmod(0o700)
    digest = hashlib.sha256(script.read_bytes()).hexdigest()
    monkeypatch.setattr(bootstrap, "PINNED_BINARY_SHA256", digest)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "SYNTHETIC_HOST_ENV_MUST_NOT_PROPAGATE")
    return BinaryPin(script, digest)


def record_sandbox_runs(monkeypatch):
    """Observe receipts from real DockerSandbox; no injected runtime or output."""
    runs, roots = [], []
    original = bootstrap.DockerSandbox.run

    def observe(self, *args, **kwargs):
        roots.append(self.root)
        receipt = original(self, *args, **kwargs)
        runs.append(receipt)
        return receipt

    monkeypatch.setattr(bootstrap.DockerSandbox, "run", observe)
    return runs, roots


def assert_owned_cleanup(runs, roots):
    import subprocess

    assert runs and all(not Path(root).exists() for root in roots)
    for run in runs:
        result = subprocess.run(
            ["docker", "ps", "--all", "--quiet", "--filter", "id=" + run.container_id],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0 and not result.stdout.strip()
    assert os.geteuid() != 0
