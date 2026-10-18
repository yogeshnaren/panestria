"""One pinned local model service: nonroot, private Unix socket, no public network."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from panestria.contracts.inference import InferenceUnavailable
from panestria.resources.primary import PrimaryLease

IMAGE = "python@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9"
MODEL = "qwen2.5:1.5b-instruct"
MODEL_DIGEST = "65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b"

# NVML inventory (including nvidia-smi) can succeed while the compute driver is
# unusable after a host suspend/driver failure. A separate trusted process keeps
# driver initialization out of the controller and puts a deadline on this probe.
_CUDA_PROBE = """import ctypes,sys
try:
 driver=ctypes.CDLL('/usr/lib/x86_64-linux-gnu/libcuda.so.1')
 driver.cuInit.argtypes=[ctypes.c_uint];driver.cuInit.restype=ctypes.c_int
 driver.cuDeviceGetCount.argtypes=[ctypes.POINTER(ctypes.c_int)];driver.cuDeviceGetCount.restype=ctypes.c_int
 count=ctypes.c_int()
 if driver.cuInit(0)!=0 or driver.cuDeviceGetCount(ctypes.byref(count))!=0 or count.value<1:sys.exit(1)
 print('CUDA_READY')
except (OSError,AttributeError):sys.exit(1)
"""


def require_gpu_driver() -> None:
    """Read-only compute readiness; never reload a module or fall back to CPU.

    This is a necessary host prerequisite, not proof of container GPU offload,
    model quality, measured performance or foreground resource isolation.
    """
    try:
        result = subprocess.run(
            [sys.executable, "-I", "-c", _CUDA_PROBE],
            cwd="/",
            env={"PATH": "/usr/bin:/bin"},
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=5,
            check=False,
        )
        if result.returncode != 0 or result.stdout != b"CUDA_READY\n" or result.stderr:
            raise InferenceUnavailable("gpu_initialization_unavailable")
    except (OSError, subprocess.TimeoutExpired):
        raise InferenceUnavailable("gpu_initialization_unavailable") from None


class ModelRuntime:
    def __init__(
        self, models: Path, socket_directory: Path, *, gpu: bool = False, preserve_existing: bool = False
    ) -> None:
        self.models, self.socket_directory, self.gpu = models.resolve(), socket_directory.resolve(), gpu
        self.primary = PrimaryLease(Path.home() / ".local/state/panestria")
        self.id: str | None = None
        self.preserve_existing = preserve_existing
        self.identity = uuid4().hex
        self.effective: dict[str, Any] = {}
        self.socket_path = self.socket_directory / "model.sock"
        self.uid, self.gid = os.getuid(), os.getgid()
        if self.uid == 0:
            raise InferenceUnavailable("nonroot_runtime_required")

    def _docker(self, args: list[str]) -> str:
        try:
            result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise InferenceUnavailable("model_runtime_unavailable") from None
        if result.returncode:
            raise InferenceUnavailable("model_runtime_operation_failed")
        return result.stdout

    def start(self) -> None:
        self.primary.acquire()
        try:
            self._start()
        except BaseException:
            if self.id is None:
                self.primary.release()
            raise

    def _reap_orphans(self) -> None:
        if self.preserve_existing:
            if self._docker(["ps", "-a", "-q", "--filter", "label=panestria.purpose=local-model"]).strip():
                raise InferenceUnavailable("existing_model_service_preserved")
            return
        containers = self._docker(
            [
                "ps",
                "-a",
                "-q",
                "--filter",
                "label=panestria.purpose=local-model",
                "--filter",
                f"label=panestria.owner_uid={self.uid}",
            ]
        ).split()
        for identity in containers:
            actual = json.loads(self._docker(["inspect", identity]))[0]
            labels = actual["Config"]["Labels"]
            runtime = labels.get("panestria.runtime", "")
            if not re.fullmatch(r"[0-9a-f]{32}", runtime) or actual["Config"]["User"] != f"{self.uid}:{self.gid}":
                raise InferenceUnavailable("model_orphan_identity_invalid")
            pid = labels.get("panestria.controller_pid", "")
            ticks = labels.get("panestria.controller_ticks", "")
            if not pid.isdigit() or not ticks.isdigit():
                raise InferenceUnavailable("model_orphan_owner_unknown")
            process = Path(f"/proc/{pid}/stat")
            if process.exists():
                body = process.read_text()
                if body[body.rfind(")") + 2 :].split()[19] == ticks:
                    raise InferenceUnavailable("primary_controller_still_running")
            # Lock ownership plus matching process birth/UID/purpose proves this
            # app's controller died. No arbitrary PID, name or container is removed.
            self._docker(["rm", "--force", "--volumes", actual["Id"]])
            bridge = next((m["Source"] for m in actual["Mounts"] if m["Destination"] == "/bridge"), None)
            if bridge is not None:
                directory = Path(bridge)
                socket_path = directory / "model.sock"
                if directory.is_symlink() or directory.stat().st_uid != self.uid or directory.stat().st_mode & 0o077:
                    raise InferenceUnavailable("model_orphan_socket_not_private")
                if socket_path.exists():
                    if not stat.S_ISSOCK(socket_path.lstat().st_mode):
                        raise InferenceUnavailable("model_orphan_socket_invalid")
                    socket_path.unlink()

    def _start(self) -> None:
        if self.id is not None:
            raise InferenceUnavailable("model_already_running")
        if self.gpu:
            require_gpu_driver()
        self._reap_orphans()
        manifest = self.models / "manifests/registry.ollama.ai/library/qwen2.5/1.5b-instruct"
        if not manifest.is_file() or hashlib.sha256(manifest.read_bytes()).hexdigest() != MODEL_DIGEST:
            raise InferenceUnavailable("model_missing_or_digest_mismatch")
        document = json.loads(manifest.read_bytes())
        for blob in [document["config"], *document["layers"]]:
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", blob["digest"]):
                raise InferenceUnavailable("model_blob_invalid")
            path = self.models / "blobs" / blob["digest"].replace(":", "-")
            if not path.is_file() or path.is_symlink() or path.stat().st_size != blob["size"]:
                raise InferenceUnavailable("model_blob_invalid")
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
            if digest.hexdigest() != blob["digest"][7:]:
                raise InferenceUnavailable("model_blob_invalid")
        for node in self.models.rglob("*"):
            if node.is_symlink():
                raise InferenceUnavailable("model_cache_link_denied")
        self.socket_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.socket_directory.stat().st_mode & 0o077 or self.socket_path.exists():
            raise InferenceUnavailable("model_socket_directory_not_private_or_busy")
        binary, libraries = Path("/usr/local/bin/ollama"), Path("/usr/local/lib/ollama")
        if not binary.is_file() or not libraries.is_dir():
            raise InferenceUnavailable("ollama_installation_missing")
        mounts = {
            "/usr/local/bin/ollama": (binary, False),
            "/usr/local/lib/ollama": (libraries, False),
            "/models": (self.models, False),
            "/bridge": (self.socket_directory, True),
            "/runtime/bridge.py": (Path(__file__).with_name("runtime_bridge.py").resolve(), False),
        }
        devices = []
        if self.gpu:
            for device in ("/dev/nvidia0", "/dev/nvidiactl", "/dev/nvidia-uvm", "/dev/nvidia-uvm-tools"):
                if not Path(device).exists():
                    raise InferenceUnavailable("gpu_runtime_unsupported")
                devices += ["--device", device]
            for library in ("libcuda.so.1", "libnvidia-ml.so.1"):
                source = Path("/usr/lib/x86_64-linux-gnu") / library
                if not source.is_file():
                    raise InferenceUnavailable("gpu_driver_library_missing")
                mounts[f"/driver/{library}"] = (source.resolve(), False)
        args = [
            "create",
            "--name",
            f"panestria-model-{self.identity}",
            "--label",
            "panestria.purpose=local-model",
            "--label",
            f"panestria.runtime={self.identity}",
            "--label",
            f"panestria.owner_uid={self.uid}",
            "--label",
            f"panestria.controller_pid={os.getpid()}",
            "--label",
            "panestria.controller_ticks=" + Path("/proc/self/stat").read_text().split(")", 1)[1].split()[19],
            "--pull",
            "never",
            "--network",
            "none",
            "--user",
            f"{self.uid}:{self.gid}",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges=true",
            "--memory",
            str(2560 * 1024 * 1024),
            "--memory-swap",
            str(2560 * 1024 * 1024),
            "--cpus",
            "2",
            "--pids-limit",
            "128",
            "--log-driver",
            "none",
            "--init",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=64m",
            "--ulimit",
            "core=0:0",
            "--ulimit",
            "nofile=128:128",
            "--entrypoint",
            "/usr/local/bin/python",
            *devices,
        ]
        for target, (source, writable) in mounts.items():
            if "," in str(source):
                raise InferenceUnavailable("runtime_path_invalid")
            args += ["--mount", f"type=bind,src={source},dst={target}" + ("" if writable else ",readonly")]
        args += [IMAGE, "-I", "/runtime/bridge.py"]
        self.id = self._docker(args).strip()
        try:
            actual = json.loads(self._docker(["inspect", self.id]))[0]
            host, config = actual["HostConfig"], actual["Config"]
            observed = {(m["Destination"], m["Source"], m["RW"]) for m in actual["Mounts"] if m["Type"] == "bind"}
            expected = {(target, str(source), writable) for target, (source, writable) in mounts.items()}
            if (
                config["User"] != f"{self.uid}:{self.gid}"
                or host["NetworkMode"] != "none"
                or not host["ReadonlyRootfs"]
                or host["Privileged"]
                or host["PortBindings"]
                or host["CapAdd"]
                or set(host["CapDrop"] or []) != {"ALL"}
                or host["Memory"] != 2560 * 1024 * 1024
                or host["MemorySwap"] != host["Memory"]
                or host["NanoCpus"] != 2_000_000_000
                or host["PidsLimit"] != 128
                or "no-new-privileges=true" not in host["SecurityOpt"]
                or observed != expected
                or config["Labels"].get("panestria.runtime") != self.identity
            ):
                raise InferenceUnavailable("model_profile_not_enforced")
            self.effective = actual
            self._docker(["start", self.id])
            deadline = time.monotonic() + 25
            while not self.socket_path.exists():
                if time.monotonic() > deadline:
                    raise InferenceUnavailable("model_cold_start_unavailable")
                time.sleep(0.1)
        except BaseException:
            self.stop()
            raise

    def stop(self) -> None:
        if self.id is None:
            self.primary.release()
            return
        actual = json.loads(self._docker(["inspect", self.id]))[0]
        if actual["Id"] != self.id or actual["Config"]["Labels"].get("panestria.runtime") != self.identity:
            raise InferenceUnavailable("model_cleanup_identity_mismatch")
        self._docker(["rm", "--force", "--volumes", self.id])
        self.id = None
        self.socket_path.unlink(missing_ok=True)
        self.primary.release()
