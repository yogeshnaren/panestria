"""Real private files/locks and restarted collectors; capacity/policy changes are fixtures."""

import hashlib
import json
import stat
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from panestria.cli import storage as cli
from panestria.cli.main import app
from panestria.kernel.goals import Actor
from panestria.resources import storage, storage_history
from panestria.resources.storage import StorageSettings
from panestria.resources.storage_history import StorageHistory
from panestria.resources.storage_status import StorageObserver

pytestmark = pytest.mark.unit


def config(tmp_path, **kwargs):
    settings = StorageSettings(
        notifications_enabled=True,
        filesystem=tmp_path,
        history_directory=tmp_path / "history",
        **kwargs,
    )
    path = tmp_path / "settings.json"
    path.write_text(settings.model_dump_json())
    path.chmod(0o600)
    return path, settings


def settle(observer):
    deadline = time.monotonic() + 3
    while observer.inflight:
        assert time.monotonic() < deadline
        time.sleep(0.002)
    return observer.value


def sample(settings):
    # Actual selected filesystem statvfs, no directory/Docker/Timeshift scans.
    return storage.inspect_storage(settings.model_copy(update={"include_timeshift": False}))


def test_restart_preserves_original_sample_and_compares_growth_and_backup_policy(tmp_path, monkeypatch):
    path, settings = config(tmp_path, include_timeshift=True)
    actor = Actor(str(uuid4()), str(uuid4()))
    first = sample(settings)
    first = replace(
        first,
        capacity=replace(first.capacity, available_bytes=20 * storage.GIB),
        timeshift={"status": "OBSERVED", "schedules": {"daily": False}},
    )
    old_disk = first.capacity
    monkeypatch.setattr(storage, "capacity", lambda _: replace(old_disk, available_bytes=10 * storage.GIB))
    monkeypatch.setattr(storage, "timeshift_settings", lambda: {"status": "OBSERVED", "schedules": {"daily": True}})
    original = StorageObserver(actor, path, probe=lambda *a, **kw: first)
    original.view(actor)
    assert "storage_history_saved" in {w.code for w in settle(original).warnings}
    original.close()
    files = list(settings.history_directory.glob("*.json"))
    assert len(files) == 1
    old = files[0].read_bytes()
    assert stat.S_IMODE(files[0].stat().st_mode) == 0o600
    assert stat.S_IMODE(settings.history_directory.stat().st_mode) == 0o700

    restarted = StorageObserver(actor, path)
    restarted.view(actor)
    view = settle(restarted)
    restarted.close()
    assert view.state == "OBSERVED" and view.capacity.available_bytes == 10 * storage.GIB
    assert {"rapid_disk_growth", "backup_policy_changed", "storage_history_saved"} <= {w.code for w in view.warnings}
    assert first.observed_at in next(w.recommendation for w in view.warnings if w.code == "storage_history_saved")
    assert files[0].read_bytes() == old and len(list(settings.history_directory.glob("*.json"))) == 2
    assert str(tmp_path) not in view.model_dump_json() and '"device"' not in view.model_dump_json()
    assert view.cleanup_authority == view.acceptance_authority == "NONE"


def test_default_and_opt_out_do_not_create_history_and_disabled_records_stay_intact(tmp_path):
    _, enabled = config(tmp_path)
    disabled = enabled.model_copy(update={"notifications_enabled": False})
    with StorageHistory(disabled) as history:
        assert history.previous() is None
        assert history.retain(sample(disabled)).warnings == sample(disabled).warnings
    assert not enabled.history_directory.exists()
    assert "history_directory" not in StorageSettings().model_dump_json()
    with StorageHistory(enabled) as history:
        history.retain(sample(enabled))
    before = {p.name: p.read_bytes() for p in enabled.history_directory.iterdir()}
    with StorageHistory(disabled) as history:
        assert history.previous() is None
    assert {p.name: p.read_bytes() for p in enabled.history_directory.iterdir()} == before


@pytest.mark.parametrize("change", ["old", "future", "collector", "settings", "filesystem"])
def test_incompatible_or_stale_history_does_not_become_a_current_baseline(tmp_path, change):
    _, settings = config(tmp_path)
    with StorageHistory(settings) as history:
        history.retain(sample(settings))
    path = next(settings.history_directory.glob("*.json"))
    body = json.loads(path.read_bytes())
    if change in {"old", "future"}:
        shift = timedelta(days=-2) if change == "old" else timedelta(hours=1)
        body["report"]["observed_at"] = (datetime.now(UTC) + shift).isoformat()
    else:
        body[change + "_sha256"] = "0" * 64
    # Preserve the original, add a differently identified fixture; no old bytes relabeled.
    raw = json.dumps(body).encode()
    fixture = settings.history_directory / (hashlib.sha256(raw).hexdigest() + ".json")
    fixture.write_bytes(raw)
    fixture.chmod(0o600)
    with StorageHistory(settings) as history:
        history.samples = (fixture,)
        assert history.previous() is None and history.state == "READY"
    assert path.exists()


def test_busy_full_and_corrupt_history_keep_current_capacity_and_never_delete(tmp_path, monkeypatch):
    _, settings = config(tmp_path)
    report = sample(settings)
    with StorageHistory(settings) as first:
        with StorageHistory(settings) as busy:
            assert busy.previous() is None
            assert "storage_history_unavailable" in {w.code for w in busy.retain(report).warnings}
        assert "storage_history_saved" in {w.code for w in first.retain(report).warnings}
    path = next(settings.history_directory.glob("*.json"))
    original = path.read_bytes()
    monkeypatch.setattr(storage_history, "MAX_FILES", 2)  # lock + one actual sample.
    with StorageHistory(settings) as full:
        assert full.previous() is not None
        current = full.retain(report)
        assert "storage_history_full" in {w.code for w in current.warnings}
        assert current.capacity == report.capacity
    assert path.read_bytes() == original
    monkeypatch.setattr(storage_history, "MAX_FILES", 512)
    monkeypatch.setattr(storage_history, "MAX_BYTES", len(original) + 1)
    with StorageHistory(settings) as byte_full:
        assert byte_full.previous() is not None
        assert "storage_history_full" in {w.code for w in byte_full.retain(report).warnings}
    assert path.read_bytes() == original
    path.write_bytes(original + b" ")
    with StorageHistory(settings) as corrupt:
        assert corrupt.previous() is None
        assert "storage_history_unavailable" in {w.code for w in corrupt.retain(report).warnings}
    assert path.read_bytes() == original + b" "


def test_unsafe_directory_and_replaced_root_cannot_write_outside_selected_history(tmp_path):
    _, settings = config(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    settings.history_directory.symlink_to(outside, target_is_directory=True)
    with StorageHistory(settings) as denied:
        assert denied.state == "UNAVAILABLE"
        denied.retain(sample(settings))
    assert list(outside.iterdir()) == []
    # Separate explicitly owned directory for the root-replacement boundary.
    other = settings.model_copy(update={"history_directory": tmp_path / "second"})
    with StorageHistory(other) as held:
        other.history_directory.rename(tmp_path / "retained")
        other.history_directory.symlink_to(outside, target_is_directory=True)
        assert "storage_history_unavailable" in {w.code for w in held.retain(sample(other)).warnings}
    assert list(outside.iterdir()) == []
    assert not list((tmp_path / "retained").glob("*.json"))
    public = settings.model_copy(update={"history_directory": tmp_path / "public"})
    public.history_directory.mkdir(mode=0o755)
    with StorageHistory(public) as denied:
        assert denied.state == "UNAVAILABLE"
    assert list(public.history_directory.iterdir()) == []


@pytest.mark.parametrize("change", ["disable", "close"])
def test_opt_out_or_shutdown_during_probe_does_not_retain_a_late_sample(tmp_path, change):
    path, settings = config(tmp_path)
    actor = Actor(str(uuid4()), str(uuid4()))

    def probe(current, **kwargs):
        if change == "disable":
            path.write_text(settings.model_copy(update={"notifications_enabled": False}).model_dump_json())
        else:
            observer.close()
        return sample(current)

    observer = StorageObserver(actor, path, probe=probe)
    observer.view(actor)
    view = settle(observer)
    assert not list(settings.history_directory.glob("*.json"))
    assert view.state == ("DISABLED" if change == "disable" else "UNAVAILABLE")
    observer.close()


def test_owner_watch_retains_one_real_capacity_sample_and_recovers_original_time(tmp_path, monkeypatch):
    path, settings = config(tmp_path)
    monkeypatch.setattr(cli.time, "sleep", lambda _: (_ for _ in ()).throw(KeyboardInterrupt()))
    result = CliRunner().invoke(app, ["storage", "watch", "--config", str(path)])
    assert result.exit_code == 0, result.output
    live = json.loads(result.output)
    assert "storage_history_saved" in {w["code"] for w in live["warnings"]}
    with StorageHistory(settings) as history:
        saved = history.previous()
        assert saved.observed_at == live["observed_at"]
        assert saved.capacity.available_bytes == live["capacity"]["available_bytes"]
        assert saved.cleanup_authority == "NONE"
