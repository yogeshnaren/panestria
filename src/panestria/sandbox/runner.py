"""Create, inspect, then run one secret-free container. Cleanup uses its exact ID."""

from __future__ import annotations

import hashlib
import json
import os
import selectors
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from panestria.sandbox.profiles import ReadOnlyMount, SandboxProfile, SandboxRejected


@dataclass(frozen=True)
class SandboxReceipt:
    container_id: str
    profile_sha256: str
    effective_config_sha256: str
    exit_code: int | None
    reason: str
    output: bytes
    elapsed_seconds: float
    oom_killed: bool


class DockerSandbox:
    def __init__(self, workspace_root: Path, *, runtime_mounts: tuple[ReadOnlyMount, ...] = ()) -> None:
        self.root = workspace_root.resolve()
        self.mounts = (
            *runtime_mounts,
            ReadOnlyMount(Path(__file__).with_name("no_network.py"), "/runtime/panestria-no-network.py"),
        )
        for mount in self.mounts:
            mount.validate()

    def _docker(self, args: list[str], *, timeout: float = 30) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(["docker", *args], text=True, capture_output=True, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise SandboxRejected("container_runtime_unavailable") from None
        if result.returncode != 0:
            # Docker diagnostics may contain host paths; do not echo them to clients.
            raise SandboxRejected("container_operation_failed")
        return result

    def run(
        self,
        workspace: Path,
        argv: tuple[str, ...],
        profile: SandboxProfile,
        *,
        attempt_id: str | None = None,
        cancel: threading.Event | None = None,
    ) -> SandboxReceipt:
        profile.validate()
        if cancel is not None and cancel.is_set():
            raise SandboxRejected("cancelled_before_start")
        if workspace.is_symlink() or not workspace.is_dir():
            raise SandboxRejected("invalid_workspace")
        workspace = workspace.resolve()
        if workspace == self.root or not workspace.is_relative_to(self.root) or "," in str(workspace):
            raise SandboxRejected("workspace_scope_denied")
        for entry in workspace.rglob("*"):
            if entry.is_symlink():
                if not entry.resolve().is_relative_to(workspace):
                    raise SandboxRejected("workspace_link_escape")
            elif entry.is_file() and entry.stat().st_nlink > 1:
                raise SandboxRejected("workspace_hardlink_denied")
            if entry.name in {".ssh", ".aws", ".credentials.json", "secrets"} or entry.name.startswith(".env"):
                raise SandboxRejected("private_workspace_path")
        if not argv or any("\x00" in arg for arg in argv) or sum(map(len, argv)) > 256_000:
            raise SandboxRejected("invalid_command")
        allowed_executables = {
            "/usr/local/bin/python",
            *(mount.destination for mount in self.mounts if mount.source.is_file()),
        }
        if argv[0] not in allowed_executables:
            raise SandboxRejected("unregistered_executable")
        identity = UUID(attempt_id) if attempt_id else uuid4()
        name = f"panestria-worker-{identity.hex}"
        image = json.loads(self._docker(["image", "inspect", profile.image]).stdout)[0]
        image_id = str(image["Id"])
        if cancel is not None and cancel.is_set():
            raise SandboxRejected("cancelled_before_start")
        args = [
            "create",
            "--name",
            name,
            "--label",
            "panestria.purpose=worker",
            "--label",
            f"panestria.attempt={identity}",
            "--pull",
            "never",
            "--network",
            "none",
            "--user",
            f"{profile.uid}:{profile.gid}",
            "--read-only",
            "--log-driver",
            "none",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges=true",
            "--memory",
            str(profile.memory_bytes),
            "--memory-swap",
            str(profile.memory_bytes),
            "--cpus",
            str(profile.cpu_nanos / 1_000_000_000),
            "--pids-limit",
            str(profile.pids),
            "--ulimit",
            "nofile=128:128",
            "--ulimit",
            "core=0:0",
            "--init",
            "--tmpfs",
            f"/tmp:rw,nosuid,nodev,size={profile.tmp_bytes},mode=1777",
            "--mount",
            f"type=bind,src={workspace},dst=/workspace" + (",readonly" if profile.workspace_readonly else ""),
            "--workdir",
            "/workspace",
            "--env",
            "HOME=/tmp/home",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--env",
            "PYTHONNOUSERSITE=1",
            "--entrypoint",
            "/usr/local/bin/python",
        ]
        for mount in self.mounts:
            args.extend(["--mount", f"type=bind,src={mount.source.resolve()},dst={mount.destination},readonly"])
        args.extend([profile.image, "-I", "/runtime/panestria-no-network.py", *argv])
        container_id = self._docker(args).stdout.strip()
        if len(container_id) != 64 or not all(char in "0123456789abcdef" for char in container_id):
            raise SandboxRejected("invalid_container_identity")
        try:
            effective = self._inspect(container_id)
            self._validate_effective(effective, image_id, workspace, profile, str(identity))
            config_hash = hashlib.sha256(
                json.dumps(effective, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            return self._execute(container_id, profile, config_hash, cancel=cancel)
        finally:
            # No task-provided process ID or container name is accepted for cleanup.
            current = self._inspect(container_id)
            if current["Id"] != container_id or current["Config"]["Labels"].get("panestria.attempt") != str(identity):
                raise SandboxRejected("cleanup_identity_mismatch")
            self._docker(["rm", "--force", "--volumes", container_id])

    def _inspect(self, container_id: str) -> dict[str, Any]:
        inspected = json.loads(self._docker(["inspect", container_id]).stdout)
        if not isinstance(inspected, list) or len(inspected) != 1 or not isinstance(inspected[0], dict):
            raise SandboxRejected("invalid_runtime_inspection")
        return inspected[0]

    def _validate_effective(
        self, actual: dict[str, Any], image_id: str, workspace: Path, profile: SandboxProfile, attempt_id: str
    ) -> None:
        host, config = actual["HostConfig"], actual["Config"]
        expected_mounts = {
            ("/workspace", str(workspace), not profile.workspace_readonly),
            *((mount.destination, str(mount.source.resolve()), False) for mount in self.mounts),
        }
        observed_mounts = {
            (entry["Destination"], entry["Source"], entry["RW"])
            for entry in actual["Mounts"]
            if entry["Type"] == "bind"
        }
        if (
            actual["Image"] != image_id
            or config["User"] != f"{profile.uid}:{profile.gid}"
            or host["Privileged"]
            or not host["ReadonlyRootfs"]
            or host["NetworkMode"] != "none"
            or host["Memory"] != profile.memory_bytes
            or host["MemorySwap"] != profile.memory_bytes
            or host["NanoCpus"] != profile.cpu_nanos
            or host["PidsLimit"] != profile.pids
            or host["CapAdd"]
            or set(host["CapDrop"] or []) != {"ALL"}
            or "no-new-privileges=true" not in host["SecurityOpt"]
            or not host["Init"]
            or config["Labels"].get("panestria.attempt") != attempt_id
            or observed_mounts != expected_mounts
            or host["LogConfig"]["Type"] != "none"
            or host.get("Devices")
            or host.get("DeviceRequests")
            or host.get("PidMode")
            or host.get("IpcMode") not in {"private", ""}
            or host.get("Binds")
        ):
            raise SandboxRejected("effective_profile_mismatch")
        inherited = [entry.split("=", 1)[0] for entry in config["Env"]]
        if any(
            name in inherited
            for name in (
                "OPENAI_API_KEY",
                "ANTHROPIC_API_KEY",
                "CLAUDE_CODE_OAUTH_TOKEN",
                "PANESTRIA_DATABASE_URL",
                "DOCKER_HOST",
            )
        ):
            raise SandboxRejected("credential_inheritance_denied")
        tmp = host["Tmpfs"].get("/tmp", "")
        if not all(option in tmp.split(",") for option in ("nosuid", "nodev", f"size={profile.tmp_bytes}")):
            raise SandboxRejected("effective_tmp_mismatch")
        if any(entry["Type"] == "volume" for entry in actual["Mounts"]):
            raise SandboxRejected("implicit_volume_denied")

    def _execute(
        self,
        container_id: str,
        profile: SandboxProfile,
        config_hash: str,
        *,
        cancel: threading.Event | None = None,
    ) -> SandboxReceipt:
        started = time.monotonic()
        if cancel is not None and cancel.is_set():
            return SandboxReceipt(
                container_id,
                profile.sha256(),
                config_hash,
                None,
                "cancelled",
                b"",
                0,
                False,
            )
        process = subprocess.Popen(
            ["docker", "start", "--attach", container_id], stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        assert process.stdout is not None
        output = bytearray()
        reason = "completed"
        selector = selectors.DefaultSelector()
        os.set_blocking(process.stdout.fileno(), False)
        selector.register(process.stdout, selectors.EVENT_READ)
        try:
            while True:
                if cancel is not None and cancel.is_set():
                    reason = "cancelled"
                    break
                remaining = profile.wall_seconds - (time.monotonic() - started)
                if remaining <= 0:
                    reason = "deadline_exceeded"
                    break
                events = selector.select(min(0.1, remaining))
                for key, _ in events:
                    chunk = os.read(key.fd, 16_384)
                    if chunk:
                        capacity = profile.output_bytes - len(output)
                        output.extend(chunk[: max(0, capacity)])
                        if len(chunk) > capacity:
                            reason = "output_limit"
                            break
                    else:
                        selector.unregister(process.stdout)
                if reason != "completed":
                    break
                if not selector.get_map():
                    # An attachment EOF does not prove the worker has exited.
                    # Continue checking cancellation/deadline until its state is
                    # stopped; otherwise a worker can close output and linger.
                    if not self._inspect(container_id)["State"]["Running"]:
                        break
                    time.sleep(min(0.05, max(0, remaining)))
            if reason != "completed" and self._inspect(container_id)["State"]["Running"]:
                try:
                    self._docker(["kill", container_id])
                except SandboxRejected:
                    if self._inspect(container_id)["State"]["Running"]:
                        raise

            if reason != "completed":
                stopped = self._inspect(container_id)["State"]
                if stopped["Running"]:
                    raise SandboxRejected("termination_unconfirmed")
                # Buffered attachment output can block docker after the container exits.
                # Stop only this attach client after proving the worker is stopped.
                if process.poll() is None:
                    process.kill()
            process.wait(timeout=5)
            state = self._inspect(container_id)["State"]
            if state["Running"]:
                raise SandboxRejected("termination_unconfirmed")
            exit_code = int(state["ExitCode"])
            if state["OOMKilled"]:
                reason = "memory_limit"
            elif reason == "completed" and exit_code != 0:
                reason = "process_failed"
            return SandboxReceipt(
                container_id,
                profile.sha256(),
                config_hash,
                exit_code,
                reason,
                bytes(output),
                time.monotonic() - started,
                bool(state["OOMKilled"]),
            )
        finally:
            selector.close()
            process.stdout.close()
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
