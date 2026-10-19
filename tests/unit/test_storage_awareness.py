"""Storage incident regressions: recommendations never become cleanup authority."""

import json
import os
import subprocess
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from panestria.cli import storage as cli
from panestria.cli.main import app
from panestria.resources import storage as s

pytestmark = pytest.mark.unit


def disk(*, free: int = 50 * s.GIB, percent: float = 50.0, device: int = 1) -> s.Capacity:
    return s.Capacity("OBSERVED", device, 100 * s.GIB, int(percent * s.GIB), free, 0, percent)


def test_default_inspection_does_not_scan_components_or_contact_docker_or_timeshift(monkeypatch):
    monkeypatch.setattr(s, "capacity", lambda _: disk())

    def forbidden(*args, **kwargs):
        raise AssertionError("opt_in_probe_was_called")

    monkeypatch.setattr(s.subprocess, "run", forbidden)
    monkeypatch.setattr(s, "timeshift_settings", forbidden)
    report = s.inspect_storage(s.StorageSettings())
    assert report.capacity.status == "OBSERVED"
    assert report.components == () and report.warnings == ()
    assert report.timeshift == {"status": "NOT_REQUESTED"}
    assert json.loads(report.to_json())["cleanup_authority"] == "NONE"


@pytest.mark.parametrize("percent,code", [(79.0, None), (80.0, "disk_high"), (90.0, "disk_critical")])
def test_capacity_thresholds_and_expected_write_reserve(monkeypatch, percent, code):
    monkeypatch.setattr(s, "capacity", lambda _: disk(percent=percent))
    report = s.inspect_storage(s.StorageSettings(), expected_write_bytes=31 * s.GIB)
    codes = {item.code for item in report.warnings}
    assert "free_reserve_at_risk" in codes
    assert (code in codes) if code else codes == {"free_reserve_at_risk"}
    assert all("No action is performed" in item.recommendation for item in report.warnings)


def test_growth_is_observed_only_on_same_filesystem_and_capacity_unknown_is_not_zero(monkeypatch):
    monkeypatch.setattr(s, "capacity", lambda _: disk(free=60 * s.GIB))
    before = s.inspect_storage(s.StorageSettings())
    monkeypatch.setattr(s, "capacity", lambda _: disk(free=50 * s.GIB))
    assert "rapid_disk_growth" in {w.code for w in s.inspect_storage(s.StorageSettings(), previous=before).warnings}
    other = replace(before, capacity=replace(before.capacity, device=2))
    assert "rapid_disk_growth" not in {w.code for w in s.inspect_storage(s.StorageSettings(), previous=other).warnings}
    monkeypatch.setattr(s, "capacity", lambda _: s.Capacity("UNKNOWN"))
    result = s.inspect_storage(s.StorageSettings())
    assert result.capacity.available_bytes is None
    assert {w.code for w in result.warnings} == {"capacity_unknown"}


def test_selected_directory_hardlinks_are_not_double_counted_and_symlinks_are_not_followed(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "payload").write_bytes(b"x" * 8192)
    before = s.directory_usage(s.StorageComponent(label="cache", path=data), s.capacity(tmp_path))
    os.link(data / "payload", data / "same_inode")
    (data / "outside").symlink_to("/", target_is_directory=True)
    after = s.directory_usage(s.StorageComponent(label="cache", path=data), s.capacity(tmp_path))
    assert before.status == after.status == "ESTIMATED"
    assert before.bytes == after.bytes and after.filesystem_share_percent is not None
    assert (
        s.directory_usage(s.StorageComponent(label="link", path=data / "outside"), s.capacity(tmp_path)).bytes is None
    )
    assert (data / "payload").read_bytes() == b"x" * 8192


@pytest.mark.parametrize("failure", ["timeout", "partial", "permission"])
def test_directory_probe_failures_do_not_present_partial_usage_as_complete(tmp_path, monkeypatch, failure):
    def run(command, **kwargs):
        assert command[0] == "/usr/bin/du" and "--no-dereference" in command and "--" in command
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, 3)
        if failure == "permission":
            raise PermissionError()
        return SimpleNamespace(returncode=1, stdout=b"1000\tignored\n")

    monkeypatch.setattr(s.subprocess, "run", run)
    result = s.directory_usage(s.StorageComponent(label="backups", path=tmp_path), disk())
    assert result.status == "UNKNOWN" and result.bytes is None and result.filesystem_share_percent is None


def test_docker_sizes_remain_daemon_wide_estimates_without_physical_percentages(monkeypatch):
    lines = [
        {"Type": name, "Size": size}
        for name, size in (
            ("Images", "40GB"),
            ("Containers", "2MB"),
            ("Local Volumes", "500MB"),
            ("Build Cache", "40GB"),
        )
    ]

    def run(command, **kwargs):
        assert command == [
            "/usr/bin/docker",
            "--host",
            "unix:///var/run/docker.sock",
            "system",
            "df",
            "--format",
            "{{json .}}",
        ]
        assert kwargs["timeout"] == 5 and "shell" not in kwargs
        return SimpleNamespace(returncode=0, stdout="\n".join(json.dumps(line) for line in lines).encode())

    monkeypatch.setenv("DOCKER_HOST", "tcp://untrusted.invalid:2375")
    monkeypatch.setattr(s.subprocess, "run", run)
    results = s.docker_usage()
    assert len(results) == 4 and results[0].bytes == 40_000_000_000
    assert all(item.filesystem_share_percent is None and item.status == "ESTIMATED" for item in results)
    monkeypatch.setattr(s, "capacity", lambda _: disk(free=10 * s.GIB, percent=90.0))
    report = s.inspect_storage(s.StorageSettings(include_docker=True))
    assert "docker_review" in {item.code for item in report.warnings}
    assert report.cleanup_authority == "NONE"


@pytest.mark.parametrize("payload", [b"", b"garbage", b"[]", b'{"Type":"Images","Size":"?"}', b"x" * 16385])
def test_missing_malformed_or_incomplete_docker_information_is_unknown(monkeypatch, payload):
    monkeypatch.setattr(s.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=payload))
    result = s.docker_usage()
    assert len(result) == 1 and result[0].status == "UNKNOWN" and result[0].bytes is None


def test_timeshift_schedule_is_read_only_and_does_not_relabel_cached_size_as_physical_usage(tmp_path):
    path = tmp_path / "timeshift.json"
    raw = json.dumps(
        {
            "schedule_daily": "false",
            "schedule_monthly": "true",
            "count_monthly": "2",
            "schedule_hourly": 0,
            "snapshot_size": "999999999999",
        }
    )
    path.write_text(raw)
    before = path.stat().st_mtime_ns
    report = s.timeshift_settings(path)
    assert report["schedules"] == {"daily": False, "monthly": True, "weekly": None, "hourly": None, "boot": None}
    assert report["retention_counts"]["monthly"] == 2
    assert report["physical_snapshot_bytes"] is None
    assert path.read_text() == raw and path.stat().st_mtime_ns == before
    link = tmp_path / "link"
    link.symlink_to(path)
    assert s.timeshift_settings(link)["status"] == "UNKNOWN"
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    assert s.timeshift_settings(fifo)["status"] == "UNKNOWN"


def test_large_selected_component_produces_review_option(monkeypatch):
    monkeypatch.setattr(s, "capacity", lambda _: disk())
    monkeypatch.setattr(
        s,
        "directory_usage",
        lambda *a: s.ComponentUsage("docker_data", "ESTIMATED", 40 * s.GIB, "ALLOCATED_BLOCKS_ESTIMATE", 40),
    )
    report = s.inspect_storage(
        s.StorageSettings(components=(s.StorageComponent(label="docker_data", path=Path("/x")),))
    )
    assert {w.code for w in report.warnings} == {"docker_data_large"}


def test_cli_watch_requires_opt_in_before_probing(monkeypatch):
    monkeypatch.setattr(cli, "_settings", lambda _: s.StorageSettings())
    monkeypatch.setattr(cli, "inspect_storage", lambda *a, **k: pytest.fail("probe_without_opt_in"))
    result = CliRunner().invoke(app, ["storage", "watch", "--config", "/missing"])
    assert result.exit_code == 1 and "enable_storage_notifications" in result.output


def test_cli_watch_deduplicates_and_respects_disabled_setting_on_reload(monkeypatch):
    enabled = s.StorageSettings(notifications_enabled=True)
    configs = iter([enabled, enabled, enabled, s.StorageSettings()])
    monkeypatch.setattr(cli, "_settings", lambda _: next(configs))
    monkeypatch.setattr(s, "capacity", lambda _: disk())
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: None)
    result = CliRunner().invoke(app, ["storage", "watch", "--config", "/private"])
    assert result.exit_code == 0, result.output
    lines = [json.loads(line) for line in result.output.splitlines()]
    assert len(lines) == 2 and lines[-1]["reason"] == "storage_notifications_disabled"
    assert lines[0]["cleanup_authority"] == "NONE"


def test_private_configuration_and_bounds(tmp_path):
    path = tmp_path / "storage.json"
    path.write_text('{"notifications_enabled": false}')
    path.chmod(0o644)
    assert CliRunner().invoke(app, ["storage", "inspect", "--config", str(path)]).exit_code == 1
    path.chmod(0o600)
    assert CliRunner().invoke(app, ["storage", "inspect", "--config", str(path)]).exit_code == 0
    for value in (
        {"interval_seconds": 1},
        {"critical_percent": 60, "warning_percent": 80},
        {"filesystem": "relative"},
        {"notifications_enabled": "true"},
        {"cleanup_enabled": True},
    ):
        with pytest.raises(ValueError):
            s.StorageSettings.model_validate_json(json.dumps(value))


def test_filesystem_reserved_blocks_are_not_owner_free_space(tmp_path, monkeypatch):
    monkeypatch.setattr(
        s.os, "statvfs", lambda _: SimpleNamespace(f_blocks=100, f_bfree=30, f_bavail=20, f_frsize=1024)
    )
    result = s.capacity(tmp_path)
    assert result.total_bytes == 102400 and result.used_bytes == 71680
    assert result.available_bytes == 20480 and result.reserved_bytes == 10240
    assert result.used_percent == round(100 * 70 / 90, 2)


def test_observed_backup_policy_change_warns_without_attributing_or_editing(monkeypatch):
    monkeypatch.setattr(s, "capacity", lambda _: disk())
    monkeypatch.setattr(s, "timeshift_settings", lambda: {"status": "OBSERVED", "schedules": {"daily": True}})
    before = s.inspect_storage(s.StorageSettings(include_timeshift=True))
    monkeypatch.setattr(s, "timeshift_settings", lambda: {"status": "OBSERVED", "schedules": {"daily": False}})
    after = s.inspect_storage(s.StorageSettings(include_timeshift=True), previous=before)
    assert {w.code for w in after.warnings} == {"backup_policy_changed"}
    assert after.cleanup_authority == "NONE"
