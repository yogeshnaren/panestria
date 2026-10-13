"""Checksum-gated readonly adapter for the attached prototype; no pulls or benchmarks."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from panestria.contracts.hardware import Accelerator, HardwareManifest

PROBE_SHA256 = "21bf9a12aa2fa499bc09a47b30430a86284aaada5a5bf1c573b9435759500b99"
ZIP_SHA256 = "bf9178cbd7800852e0167452900659f5a8238eb71754aa3b7944117ef35ceba6"
MEMBER = "agentos-skills/skills/hardware-probe/scripts/hwprobe.py"
PRESETS = ("lite-16gb", "omen-8gb", "omen-12gb", "omen-16gb", "mac-studio-512")


class ProbeUnavailable(Exception):
    pass


class HardwareProbe:
    def __init__(self, archive: Path, catalog_version: str = "local-ask-v1") -> None:
        self.archive, self.catalog_version = archive, catalog_version

    def collect(self, *, preset: str | None = None, tool_path: str = "/usr/bin:/bin") -> HardwareManifest:
        if os.geteuid() == 0:
            raise ProbeUnavailable("unprivileged_probe_required")
        if preset is not None and preset not in PRESETS:
            raise ProbeUnavailable("unknown_preset")
        if hashlib.sha256(self.archive.read_bytes()).hexdigest() != ZIP_SHA256:
            raise ProbeUnavailable("probe_archive_mismatch")
        with zipfile.ZipFile(self.archive) as archive:
            source = archive.read(MEMBER)
        if hashlib.sha256(source).hexdigest() != PROBE_SHA256:
            raise ProbeUnavailable("probe_source_mismatch")
        with tempfile.TemporaryDirectory(prefix="panestria-probe-") as folder:
            root = Path(folder)
            script, result = root / "hwprobe.py", root / "observation.json"
            script.write_bytes(source)
            command = [sys.executable, "-I", str(script), "--json", str(result)]
            if preset:
                command += ["--preset", preset]
            try:
                process = subprocess.run(
                    command,
                    env={"PATH": tool_path, "HOME": folder, "LANG": "C.UTF-8"},
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                raise ProbeUnavailable("probe_timeout_or_unsupported") from None
            if process.returncode or not result.exists() or result.stat().st_size > 65536:
                raise ProbeUnavailable("probe_failed")
            raw = json.loads(result.read_text())["hardware"]
        # Discard prototype model assignments/host-offload budgets: they use total RAM
        # and estimated bandwidth, neither proves foreground fit or actual throughput.
        gpus = tuple(
            Accelerator(
                vendor=g["vendor"],
                name=g["name"],
                total_gib=g.get("vram_gb") or None,
                free_gib=g.get("free_gb"),
                driver=g.get("driver"),
                bandwidth_estimate_gbs=g.get("bandwidth_gbs"),
            )
            for g in raw["gpus"]
        )
        return HardwareManifest(
            observed_at=datetime.now(UTC),
            simulated=preset is not None,
            preset=preset,
            os=raw["os"],
            arch=raw["arch"],
            kernel="SIMULATED" if preset else platform.release(),
            cpu=raw["cpu"],
            logical_cores=raw["logical_cores"],
            ram_total_gib=raw["ram_gb"] or None,
            ram_available_gib=raw["ram_available_gb"],
            disk_free_gib=raw["disk_free_gb"],
            accelerators=gpus,
            on_ac_power=raw["on_ac_power"],
            gpu_status="OBSERVED" if gpus else "NONE_OR_UNSUPPORTED",
            probe_sha256=PROBE_SHA256,
            catalog_version=self.catalog_version,
        )
