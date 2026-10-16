"""Exact-owned Docker fault fixtures; transport faults are explicitly injected."""

import json
import os
import subprocess
from contextlib import contextmanager
from uuid import uuid4

from panestria.sandbox.profiles import DEFAULT_IMAGE, SandboxProfile, SandboxRejected
from panestria.sandbox.runner import DockerSandbox, SandboxLaunchReference


def docker(*args):
    result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, "owned_launch_fixture_operation_failed"
    return result.stdout


def exists(identifier):
    return bool(docker("ps", "--all", "--quiet", "--no-trunc", "--filter", "id=" + identifier).strip())


def setup(tmp_path):
    root = tmp_path / "attempts"
    root.mkdir(mode=0o700)
    workspace = root / "workspace"
    workspace.mkdir(mode=0o700)
    profile = SandboxProfile(uid=os.getuid(), gid=os.getgid(), wall_seconds=3)
    return root, workspace, profile


@contextmanager
def stopped_container(*, name, labels):
    fixture = uuid4().hex
    args = [
        "create",
        "--name",
        name,
        "--pull",
        "never",
        "--network",
        "none",
        "--read-only",
        "--log-driver",
        "none",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges=true",
        "--memory",
        "64m",
        "--memory-swap",
        "64m",
        "--pids-limit",
        "16",
        "--cpus",
        "0.1",
        "--label",
        "panestria.reconciliation_test=" + fixture,
    ]
    for key, value in labels.items():
        args.extend(["--label", key + "=" + value])
    identifier = docker(*args, "--entrypoint", "/usr/local/bin/python", DEFAULT_IMAGE, "--version").strip()
    try:
        assert json.loads(docker("inspect", identifier))[0]["State"]["Status"] == "created"
        yield identifier
    finally:
        if exists(identifier):
            current = json.loads(docker("inspect", identifier))[0]
            assert (
                current["Id"] == identifier and current["Config"]["Labels"]["panestria.reconciliation_test"] == fixture
            )
            docker("rm", "--force", "--volumes", identifier)


class FaultyCreate(DockerSandbox):
    """Actual create/remove and runtime execution; only selected replies are injected."""

    def __init__(self, root, *, reply="error", foreign=None, query_error=False, remove_error=False):
        super().__init__(root)
        self.reply, self.foreign = reply, foreign
        self.query_error, self.remove_error = query_error, remove_error
        self.created = []
        self.references = []
        self.executed = 0

    def _docker(self, args, *, timeout=30):
        if args[0] == "ps" and self.query_error:
            raise SandboxRejected("container_runtime_unavailable")
        if args[0] == "rm" and self.remove_error == "before":
            raise SandboxRejected("container_runtime_unavailable")
        result = super()._docker(args, timeout=timeout)
        if args[0] == "create":
            identifier = result.stdout.strip()
            self.created.append(identifier)
            actual = json.loads(docker("inspect", identifier))[0]
            labels = actual["Config"]["Labels"]
            self.references.append(
                SandboxLaunchReference(
                    labels["panestria.attempt"],
                    labels["panestria.launch"],
                    labels["panestria.profile"],
                    actual["Image"],
                )
            )
            if self.reply == "error":
                raise SandboxRejected("container_runtime_unavailable")
            if self.reply == "malformed":
                return subprocess.CompletedProcess(result.args, 0, "unparseable-id\n", "")
            if self.reply == "foreign":
                return subprocess.CompletedProcess(result.args, 0, self.foreign + "\n", "")
        if args[0] == "rm" and self.remove_error and self.remove_error != "before":
            raise SandboxRejected("container_runtime_unavailable")
        return result

    def _execute(self, *args, **kwargs):
        self.executed += 1
        return super()._execute(*args, **kwargs)

    def cleanup_fixture(self):
        for identifier, reference in zip(self.created, self.references, strict=True):
            if exists(identifier):
                actual = json.loads(docker("inspect", identifier))[0]
                assert self._owned_launch(actual, identifier, reference)
                docker("rm", "--force", "--volumes", identifier)
