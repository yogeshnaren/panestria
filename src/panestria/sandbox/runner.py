"""Create, inspect, then run one secret-free container. Cleanup uses its exact ID."""

from __future__ import annotations

import hashlib
import json
import os
import re
import selectors
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from panestria.sandbox.native_tool_input import MAX_FRAME_BYTES
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


@dataclass(frozen=True)
class SandboxLaunchReference:
    """Trusted-controller reconciliation metadata, never worker-supplied authority."""

    attempt_id: str
    launch_id: str
    profile_sha256: str
    image_id: str

    @property
    def name(self) -> str:
        return "panestria-worker-" + UUID(self.attempt_id).hex

    def validate(self) -> None:
        try:
            identifiers = (UUID(self.attempt_id), UUID(self.launch_id))
            valid = (
                all(
                    str(value) == original
                    for value, original in zip(identifiers, (self.attempt_id, self.launch_id), strict=True)
                )
                and identifiers[1].version == 4
                and re.fullmatch(r"[0-9a-f]{64}", self.profile_sha256) is not None
                and re.fullmatch(r"sha256:[0-9a-f]{64}", self.image_id) is not None
            )
        except (ValueError, TypeError, AttributeError):
            valid = False
        if not valid:
            raise SandboxRejected("invalid_launch_reference")


@dataclass(frozen=True)
class LaunchReconciliation:
    status: Literal["REMOVED", "NOT_OBSERVED", "UNCONFIRMED"]
    container_id: str | None
    reason: str


class SandboxLaunchUncertain(SandboxRejected):
    def __init__(self, reference: SandboxLaunchReference, reconciliation: LaunchReconciliation) -> None:
        self.reference, self.reconciliation = reference, reconciliation
        super().__init__("sandbox_launch_reconciliation_required")


class DockerSandbox:
    def __init__(
        self,
        workspace_root: Path,
        *,
        runtime_mounts: tuple[ReadOnlyMount, ...] = (),
        on_launch: Callable[[SandboxLaunchReference, SandboxProfile], None] | None = None,
        before_start: Callable[[], None] | None = None,
    ) -> None:
        self.root = workspace_root.resolve()
        self._on_launch, self._before_start = on_launch, before_start
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
        input_frame: bytes | None = None,
    ) -> SandboxReceipt:
        profile.validate()
        if (profile.stdin_mode == "closed" and input_frame is not None) or (
            profile.stdin_mode == "native-frame-v1"
            and (type(input_frame) is not bytes or not 1 <= len(input_frame) <= MAX_FRAME_BYTES)
        ):
            raise SandboxRejected("sandbox_input_binding_mismatch")
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
        launch = SandboxLaunchReference(str(identity), str(uuid4()), profile.sha256(), image_id)
        launch.validate()
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
            "--label",
            f"panestria.launch={launch.launch_id}",
            "--label",
            f"panestria.profile={launch.profile_sha256}",
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
        if profile.stdin_mode == "native-frame-v1":
            args.extend(["--interactive", "--attach", "stdin", "--attach", "stdout", "--attach", "stderr"])
        args.extend([profile.image, "-I", "/runtime/panestria-no-network.py", *argv])
        if self._on_launch is not None:
            try:
                self._on_launch(launch, profile)  # Must commit before returning.
            except Exception:
                raise SandboxRejected("launch_intent_unconfirmed") from None
        if cancel is not None and cancel.is_set():
            raise SandboxRejected("cancelled_before_start")
        try:
            container_id = self._docker(args).stdout.strip()
            if re.fullmatch(r"[0-9a-f]{64}", container_id) is None:
                raise SandboxRejected("invalid_container_identity")
            effective = self._inspect(container_id)
            if not self._owned_launch(effective, container_id, launch):
                raise SandboxRejected("launch_identity_mismatch")
        except SandboxRejected:
            # Create can commit before its client loses the reply. The launch
            # nonce distinguishes this request even from the same attempt/name.
            observed = self.reconcile_launch(launch)
            raise SandboxLaunchUncertain(launch, observed) from None
        try:
            self._validate_effective(effective, image_id, workspace, profile, str(identity))
            if self._before_start is not None:
                try:
                    self._before_start()
                except Exception:
                    raise SandboxRejected("launch_start_authority_unconfirmed") from None
            config_hash = hashlib.sha256(
                json.dumps(effective, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            return self._execute(container_id, profile, config_hash, cancel=cancel, input_frame=input_frame)
        finally:
            observed = self.reconcile_launch(launch, expected_container_id=container_id)
            if observed.status != "REMOVED":
                raise SandboxLaunchUncertain(launch, observed)

    @staticmethod
    def _owned_launch(actual: dict[str, Any], identifier: str, reference: SandboxLaunchReference) -> bool:
        try:
            labels = actual["Config"]["Labels"]
            return bool(
                actual["Id"] == identifier
                and actual["Name"] == "/" + reference.name
                and actual["Image"] == reference.image_id
                and labels["panestria.purpose"] == "worker"
                and labels["panestria.attempt"] == reference.attempt_id
                and labels["panestria.launch"] == reference.launch_id
                and labels["panestria.profile"] == reference.profile_sha256
            )
        except (KeyError, TypeError):
            return False

    def reconcile_launch(
        self, reference: SandboxLaunchReference, *, expected_container_id: str | None = None
    ) -> LaunchReconciliation:
        """Reinspect/remove only this nonce's exact owned resource; never start or retry.

        NOT_OBSERVED is an observation, not proof a delayed create cannot arrive.
        A durable caller must retain its launch intent before dispatch; this
        component alone cannot recover a killed controller's in-memory nonce.
        """
        if not isinstance(reference, SandboxLaunchReference):
            raise SandboxRejected("invalid_launch_reference")
        reference.validate()
        if expected_container_id is not None and (
            type(expected_container_id) is not str or re.fullmatch(r"[0-9a-f]{64}", expected_container_id) is None
        ):
            raise SandboxRejected("invalid_container_identity")
        try:
            matches = self._docker(
                ["ps", "--all", "--quiet", "--no-trunc", "--filter", "label=panestria.launch=" + reference.launch_id]
            ).stdout.splitlines()
            if not matches:
                return LaunchReconciliation("NOT_OBSERVED", None, "no_owned_container_observed")
            if len(matches) != 1 or re.fullmatch(r"[0-9a-f]{64}", matches[0]) is None:
                return LaunchReconciliation("UNCONFIRMED", None, "launch_candidates_unconfirmed")
            identifier = matches[0]
            if (expected_container_id is not None and identifier != expected_container_id) or not self._owned_launch(
                self._inspect(identifier), identifier, reference
            ):
                return LaunchReconciliation("UNCONFIRMED", None, "launch_identity_unconfirmed")
            self._docker(["rm", "--force", "--volumes", identifier])
            remains = self._docker(["ps", "--all", "--quiet", "--no-trunc", "--filter", "id=" + identifier]).stdout
            if remains.strip():
                return LaunchReconciliation("UNCONFIRMED", identifier, "launch_removal_unconfirmed")
            return LaunchReconciliation("REMOVED", identifier, "owned_container_removed")
        except (SandboxRejected, ValueError, TypeError, KeyError):
            return LaunchReconciliation("UNCONFIRMED", None, "launch_runtime_unconfirmed")

    def _inspect(self, container_id: str) -> dict[str, Any]:
        try:
            inspected = json.loads(self._docker(["inspect", container_id]).stdout)
        except ValueError:
            raise SandboxRejected("invalid_runtime_inspection") from None
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
            or config.get("OpenStdin") is not (profile.stdin_mode == "native-frame-v1")
            or config.get("AttachStdin") is not (profile.stdin_mode == "native-frame-v1")
            or config.get("StdinOnce") is not (profile.stdin_mode == "native-frame-v1")
            or config.get("Tty") is not False
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
        input_frame: bytes | None = None,
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
        args = ["docker", "start", "--attach"]
        if input_frame is not None:
            args.append("--interactive")
        process = subprocess.Popen(
            [*args, container_id],
            stdin=subprocess.PIPE if input_frame is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        assert process.stdout is not None
        output = bytearray()
        reason = "completed"
        selector = selectors.DefaultSelector()
        pending = memoryview(input_frame if input_frame is not None else b"")
        input_open = process.stdin is not None
        output_open = True

        def close_input() -> None:
            nonlocal input_open
            if input_open:
                assert process.stdin is not None
                try:
                    selector.unregister(process.stdin)
                except KeyError:
                    pass  # Setup failed before stdin registration.
                # os.write bypasses the buffered file object, so close cannot
                # flush blocked payload bytes or need a writer thread.
                process.stdin.close()
                input_open = False

        try:
            os.set_blocking(process.stdout.fileno(), False)
            selector.register(process.stdout, selectors.EVENT_READ, "output")
            if process.stdin is not None:
                os.set_blocking(process.stdin.fileno(), False)
                selector.register(process.stdin, selectors.EVENT_WRITE, "input")
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
                    if key.data == "input":
                        try:
                            count = os.write(key.fd, pending[:16_384])
                        except BlockingIOError:
                            continue
                        except BrokenPipeError:
                            reason = "input_incomplete"
                            close_input()
                            break
                        if count <= 0:
                            reason = "input_incomplete"
                            close_input()
                            break
                        pending = pending[count:]
                        if not pending:
                            close_input()  # EOF after the last queued byte.
                        continue
                    chunk = os.read(key.fd, 16_384)
                    if chunk:
                        capacity = profile.output_bytes - len(output)
                        output.extend(chunk[: max(0, capacity)])
                        if len(chunk) > capacity:
                            reason = "output_limit"
                            break
                    else:
                        selector.unregister(process.stdout)
                        output_open = False
                if reason != "completed":
                    break
                if not output_open:
                    # An attachment EOF does not prove the worker has exited.
                    # Continue checking cancellation/deadline until its state is
                    # stopped; otherwise a worker can close output and linger.
                    if not self._inspect(container_id)["State"]["Running"]:
                        if pending:
                            reason = "input_incomplete"
                        break
                    time.sleep(min(0.05, max(0, remaining)))
            close_input()
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
            close_input()
            selector.close()
            process.stdout.close()
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
