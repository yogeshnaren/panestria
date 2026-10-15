"""Actual Linux CPU observations without GPU tools and bounded probe descendants."""

from __future__ import annotations

import hashlib
import os
import sys
import time
from pathlib import Path

import pytest

from panestria.resources import hardware
from panestria.resources.admission import admit
from panestria.resources.hardware import HardwareProbe, ProbeUnavailable

ARCHIVE = Path(__file__).resolve().parents[2] / "docs/specification/attachments/agentos-skills-v0.1.0.zip"


def test_actual_cpu_snapshot_is_not_a_simulation_or_a_gpu_capacity_claim(monkeypatch, tmp_path):
    before = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    trap = tmp_path / "nvidia-smi"
    marker = tmp_path / "unexpected-gpu-query"
    trap.write_text(f"#!/bin/sh\necho unexpected > '{marker}'\n")
    trap.chmod(0o700)
    monkeypatch.setenv("PATH", str(tmp_path))
    manifest = HardwareProbe(ARCHIVE).collect_cpu()
    assert not manifest.simulated and manifest.preset is None
    assert manifest.gpu_status == "NOT_PROBED_CPU_ONLY" and manifest.accelerators == ()
    assert manifest.logical_cores == os.cpu_count() and manifest.ram_available_gib is not None
    assert manifest.ram_total_gib > 0 and manifest.disk_free_gib is not None
    assert manifest.observed_at.tzinfo is not None and not marker.exists()
    assert admit(manifest, gpu=True).decision != "PERMIT"
    assert hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() == before


def test_cpu_mode_unknown_resource_values_still_deny():
    manifest = HardwareProbe(ARCHIVE).collect_cpu()
    assert admit(manifest.model_copy(update={"ram_available_gib": None}), gpu=False).decision == "UNAVAILABLE"
    assert admit(manifest.model_copy(update={"on_ac_power": None}), gpu=False).decision == "UNAVAILABLE"
    assert admit(manifest.model_copy(update={"disk_free_gib": None}), gpu=False).decision == "UNAVAILABLE"


def test_deadline_kills_only_owned_probe_group_and_does_not_wait_for_inherited_pipes(tmp_path, monkeypatch):
    marker = tmp_path / "owned-helper-pid"
    tool = tmp_path / "nvidia-smi"
    tool.write_text(
        f"#!{sys.executable}\nimport os,time\nopen({str(marker)!r},'w').write(str(os.getpid()))\ntime.sleep(60)\n"
    )
    tool.chmod(0o700)
    monkeypatch.setattr(hardware, "PROBE_DEADLINE_SECONDS", 0.5)
    started = time.monotonic()
    with pytest.raises(ProbeUnavailable, match="probe_timeout_or_unsupported"):
        HardwareProbe(ARCHIVE).collect(tool_path=str(tmp_path))
    assert time.monotonic() - started < 2
    assert marker.exists()
    pid = int(marker.read_text())
    # A killed orphan may briefly be a zombie until init reaps it; it must not
    # remain an executing descendant. No other process identity is signaled.
    state = Path(f"/proc/{pid}/stat")
    assert not state.exists() or state.read_text().split(")", 1)[1].split()[0] == "Z"
