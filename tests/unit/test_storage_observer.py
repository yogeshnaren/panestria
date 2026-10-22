"""Opt-in, bounded sampling and publication fences; controlled clock/probe only."""

import json
import threading
import time
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from panestria.config_local import LocalApplicationRejected
from panestria.config_storage import load_storage_settings
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.resources.storage import Capacity, StorageReport, StorageSettings
from panestria.resources.storage_status import StorageObserver

pytestmark = pytest.mark.unit


def private_settings(path, *, enabled=True, interval=300):
    settings = StorageSettings(notifications_enabled=enabled, interval_seconds=interval)
    path.write_text(settings.model_dump_json())
    path.chmod(0o600)
    return settings


def settle(observer):
    deadline = time.monotonic() + 3
    while True:
        with observer.lock:
            if not observer.inflight:
                return observer.value
        assert time.monotonic() < deadline, "collector did not settle"
        time.sleep(0.002)


def sample(settings, **kwargs):
    return StorageReport(
        datetime.now(UTC).isoformat(),
        str(settings.filesystem),
        Capacity("OBSERVED", 1234, 1000, 200, 750, 50, 21.05),
        (),
        {"status": "NOT_REQUESTED"},
        (),
    )


def test_disabled_configuration_and_foreign_actor_never_probe(tmp_path):
    path = tmp_path / "private.json"
    private_settings(path, enabled=False)
    actor = Actor(str(uuid4()), str(uuid4()))
    observer = StorageObserver(actor, path, probe=lambda *a, **k: pytest.fail("probe without opt-in"))
    with pytest.raises(KernelDenied):
        observer.view(Actor(actor.owner_id, str(uuid4())))
    assert not observer.inflight
    assert observer.view(actor).state == "COLLECTING"
    assert settle(observer).state == "DISABLED"
    assert observer.view(actor).notifications_enabled is False
    observer.close()


def test_concurrent_views_coalesce_and_configured_interval_does_not_mean_repeated_full_probes(tmp_path):
    path = tmp_path / "private.json"
    private_settings(path)
    actor = Actor(str(uuid4()), str(uuid4()))
    clock = SimpleNamespace(now=1.0)
    entered, release = threading.Event(), threading.Event()
    calls = []

    def probe(settings, **kwargs):
        calls.append(threading.get_ident())
        entered.set()
        assert release.wait(3)
        return sample(settings)

    observer = StorageObserver(actor, path, probe=probe, clock=lambda: clock.now)
    try:
        assert observer.view(actor).state == "COLLECTING"  # Must return while probe is held.
        assert entered.wait(3)
        for _ in range(20):
            assert observer.view(actor).state == "COLLECTING"
        assert len(calls) == 1 and calls[0] != threading.get_ident()
        release.set()
        value = settle(observer)
        assert value.state == "OBSERVED" and value.capacity.available_bytes == 750
        assert value.sample_interval_seconds == 300
        assert "device" not in value.model_dump_json() and '"filesystem"' not in value.model_dump_json()
        clock.now = 61
        observer.view(actor)
        assert settle(observer).observed_at == value.observed_at and len(calls) == 1
        clock.now = 301
        observer.view(actor)
        assert settle(observer).state == "OBSERVED" and len(calls) == 2
        private_settings(path, enabled=False)
        clock.now = 361
        observer.view(actor)
        assert settle(observer).state == "DISABLED" and len(calls) == 2
    finally:
        release.set()
        observer.close()


@pytest.mark.parametrize("change", ["disabled", "different", "closed"])
def test_changed_policy_or_close_discards_an_already_running_collection(tmp_path, change):
    path = tmp_path / "private.json"
    private_settings(path)
    actor = Actor(str(uuid4()), str(uuid4()))
    entered, release = threading.Event(), threading.Event()

    def probe(settings, **kwargs):
        entered.set()
        assert release.wait(3)
        return sample(settings)

    observer = StorageObserver(actor, path, probe=probe)
    try:
        observer.view(actor)
        assert entered.wait(3)
        if change == "closed":
            observer.close()
        else:
            private_settings(path, enabled=change != "disabled", interval=600)
        release.set()
        value = settle(observer)
        assert value.state == ("DISABLED" if change == "disabled" else "UNAVAILABLE")
        assert value.observed_at is None and value.capacity is None and observer.previous is None
        if change == "closed":
            assert observer.view(actor).reason == "closed"
    finally:
        release.set()
        observer.close()


def test_stalled_collector_never_starts_a_replacement_and_late_results_are_not_current(tmp_path):
    path = tmp_path / "private.json"
    private_settings(path)
    actor = Actor(str(uuid4()), str(uuid4()))
    clock = SimpleNamespace(now=1.0)
    entered, release = threading.Event(), threading.Event()
    calls = []

    def probe(settings, **kwargs):
        calls.append(True)
        entered.set()
        assert release.wait(3)
        return sample(settings)

    observer = StorageObserver(actor, path, probe=probe, clock=lambda: clock.now)
    try:
        observer.view(actor)
        assert entered.wait(3)
        clock.now = 1000
        for _ in range(20):
            assert observer.view(actor).state == "STALLED"
        assert len(calls) == 1
        release.set()
        value = settle(observer)
        assert value.reason == "probe_deadline_exceeded" and value.capacity is None
        assert observer.previous is None
    finally:
        release.set()
        observer.close()


def test_private_config_rejects_links_public_permissions_and_oversize_without_exposing_errors(tmp_path):
    path = tmp_path / "private.json"
    private_settings(path)
    link = tmp_path / "link.json"
    link.symlink_to(path)
    with pytest.raises(LocalApplicationRejected):
        load_storage_settings(link)
    path.chmod(0o644)
    actor = Actor(str(uuid4()), str(uuid4()))
    observer = StorageObserver(actor, path, probe=lambda *a, **k: pytest.fail("untrusted config probe"))
    observer.view(actor)
    value = settle(observer)
    assert value.state == "UNAVAILABLE"
    assert str(path) not in value.model_dump_json() and "Permission" not in value.model_dump_json()
    observer.close()
    path.chmod(0o600)
    path.write_text(json.dumps({"private": "x" * 16384}))
    with pytest.raises(LocalApplicationRejected):
        load_storage_settings(path)
