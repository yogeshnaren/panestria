"""Attached simulated profiles, unavailable tools and actual readonly observations."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from panestria.resources.catalog import ModelCandidate, propose
from panestria.resources.hardware import PRESETS, PROBE_SHA256, HardwareProbe
from panestria.resources.manifests import ManifestStore

ARCHIVE = Path(__file__).resolve().parents[2] / "docs/specification/attachments/agentos-skills-v0.1.0.zip"


def test_five_presets_and_missing_tools(record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-015-TC01")
    record_property("source_clauses", "AOS-015-F01,AOS-015-AC02")
    probe = HardwareProbe(ARCHIVE)
    for preset in PRESETS:
        result = probe.collect(preset=preset)
        assert result.simulated and result.preset == preset and result.probe_sha256 == PROBE_SHA256
        assert all(g.bandwidth_measured_gbs is None for g in result.accelerators)
        assert propose(result).tokens_per_second_measured is None
    result = probe.collect(tool_path="/nonexistent")
    assert result.gpu_status == "NONE_OR_UNSUPPORTED" and result.accelerators == ()
    assert result.ram_total_gib is not None and result.ram_total_gib > 0


def test_model_fit_uncertainty(record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-015-TC02")
    record_property("source_clauses", "AOS-015-F03,AOS-015-AC02")
    manifest = HardwareProbe(ARCHIVE).collect(preset="omen-8gb")
    assert propose(manifest).state == "GPU_CANDIDATE"
    assert propose(manifest.model_copy(update={"ram_available_gib": None})).reasons == ("capacity_unknown",)
    assert propose(manifest.model_copy(update={"ram_available_gib": 1.0})).state == "UNAVAILABLE"
    huge = ModelCandidate("user-pin", 28.0, 0.5, 1.0, ("chat",), "Apache-2.0", "publisher.example/model")
    fit = propose(manifest, pin=huge)
    assert fit.state == "UNAVAILABLE" and fit.model_ref == huge.model_ref and fit.resident_estimate_gib == 30.0
    assert propose(manifest.model_copy(update={"accelerators": ()})).state == "CPU_CANDIDATE"
    assert propose(manifest.model_copy(update={"on_ac_power": False})).state == "UNAVAILABLE"
    assert propose(manifest.model_copy(update={"thermal_state": "HOT"})).reasons == ("thermal_pressure",)


@pytest.mark.live
def test_real_hardware_read_only(record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-015-TC03")
    record_property("source_clauses", "AOS-015-F01,AOS-015-F02,AOS-015-AC01,AOS-015-AC03")
    record_property("execution_mode", "LIVE")
    before = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    result = HardwareProbe(ARCHIVE).collect()
    assert not result.simulated and result.permissions == "READ_ONLY_UNPRIVILEGED"
    assert result.ram_total_gib is not None and result.ram_available_gib is not None
    assert result.kernel and result.observed_at.tzinfo is not None
    assert result.accelerators and "RTX 4060" in result.accelerators[0].name
    assert 7.0 < result.accelerators[0].total_gib < 9.0 and result.accelerators[0].driver
    assert result.on_ac_power is True and hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() == before
    record_property("hardware_manifest", result.model_dump_json())


def test_manifest_version_change(tmp_path: Path, record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-015-TC04")
    record_property("source_clauses", "AOS-015-F02,AOS-015-F04")
    store = ManifestStore(tmp_path / "manifests", b"synthetic-local-signing-key-only-32")
    first = HardwareProbe(ARCHIVE).collect(preset="omen-8gb")
    old = store.write(first)
    newer = first.model_copy(update={"catalog_version": "local-ask-v2"})
    new = store.write(newer)
    assert old != new and store.read(old) == first and store.read(new) == newer
    assert store.changes(old, new) == ("catalog_version",)
    path = store.directory / f"{new}.json"
    path.write_text(path.read_text().replace("local-ask-v2", "tampered"))
    with pytest.raises(ValueError, match="signature_mismatch"):
        store.read(new)
