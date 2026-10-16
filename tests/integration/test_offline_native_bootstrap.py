"""Actual Docker/seccomp/mount behavior with an explicit synthetic native fixture."""

import hashlib
import json
import subprocess
import threading
import time

import pytest

from native_bootstrap_support import assert_owned_cleanup, record_sandbox_runs, synthetic_pin
from panestria.brokers.harness import native_bootstrap as bootstrap


def test_synthetic_metadata_observes_actual_offline_secret_free_envelope_and_cleanup(
    tmp_path, monkeypatch, record_property
):
    pin = synthetic_pin(tmp_path, monkeypatch)
    before = hashlib.sha256(pin.path.read_bytes()).hexdigest()
    runs, roots = record_sandbox_runs(monkeypatch)
    result = bootstrap.NativeBootstrap().inspect(pin)
    assert result.status == "BOOTSTRAP_ONLY" and not result.authentication_observed
    assert not result.inference_observed and not result.runtime_authority
    assert result.binary_sha256 == before and len(result.runs) == len(runs) == 2
    assert tuple(run.mode for run in result.runs) == ("version", "help")
    assert result.controls == tuple(sorted(bootstrap.VISIBLE_CONTROLS))
    assert all(run.reason == "completed" and run.exit_code == 0 for run in runs)
    assert hashlib.sha256(pin.path.read_bytes()).hexdigest() == before
    assert_owned_cleanup(runs, roots)
    record_property(
        "scope", "actual Docker/seccomp/nonroot/RO/cgroup/env/sentinel; synthetic native fixture, no Claude"
    )


@pytest.mark.parametrize(
    "behavior,reason",
    [
        ("wrong-version", "version_mismatch"),
        ("missing-controls", "controls_missing"),
        ("invalid-utf8", "unavailable"),
        ("fail", "failed"),
        ("pressure", "output_limit"),
        ("timeout", "deadline_exceeded"),
        ("closed-output", "deadline_exceeded"),
    ],
)
def test_real_container_failures_do_not_become_metadata_success(tmp_path, monkeypatch, behavior, reason):
    pin = synthetic_pin(tmp_path, monkeypatch, behavior=behavior)
    runs, roots = record_sandbox_runs(monkeypatch)
    with pytest.raises(bootstrap.NativeBootstrapUnavailable, match="native_bootstrap_" + reason):
        bootstrap.NativeBootstrap().inspect(
            pin, wall_seconds=0.2 if "timeout" in behavior or behavior == "closed-output" else 3
        )
    assert_owned_cleanup(runs, roots)


@pytest.mark.parametrize("target", ["source", "snapshot"])
def test_actual_post_run_binary_mutation_invalidates_bootstrap(tmp_path, monkeypatch, target):
    pin = synthetic_pin(tmp_path, monkeypatch)
    runs, roots = record_sandbox_runs(monkeypatch)
    original = bootstrap.DockerSandbox.run

    def mutate(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        path = pin.path if target == "source" else self.mounts[0].source
        path.chmod(0o700)
        path.write_bytes(b"synthetic-test-only-mutation")
        return result

    monkeypatch.setattr(bootstrap.DockerSandbox, "run", mutate)
    with pytest.raises(bootstrap.NativeBootstrapUnavailable, match="native_bootstrap_unavailable"):
        bootstrap.NativeBootstrap().inspect(pin)
    assert len(runs) == 1
    assert_owned_cleanup(runs, roots)


def test_cancellation_after_actual_container_started_stops_only_its_owned_process(tmp_path, monkeypatch):
    pin = synthetic_pin(tmp_path, monkeypatch, behavior="timeout")
    runs, roots = record_sandbox_runs(monkeypatch)
    cancel, seen_running = threading.Event(), threading.Event()
    watchers = []
    original = bootstrap.DockerSandbox._execute

    def execute(self, identifier, *args, **kwargs):
        def watch():
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                process = subprocess.run(["docker", "inspect", identifier], capture_output=True, timeout=5)
                if process.returncode == 0 and json.loads(process.stdout)[0]["State"]["Running"]:
                    seen_running.set()
                    cancel.set()
                    return
                time.sleep(0.02)

        watcher = threading.Thread(target=watch, daemon=True)
        watchers.append(watcher)
        watcher.start()
        return original(self, identifier, *args, **kwargs)

    monkeypatch.setattr(bootstrap.DockerSandbox, "_execute", execute)
    with pytest.raises(bootstrap.NativeBootstrapUnavailable, match="native_bootstrap_cancelled"):
        bootstrap.NativeBootstrap().inspect(pin, wall_seconds=5, cancel=cancel)
    for watcher in watchers:
        watcher.join(timeout=5)
    assert seen_running.is_set() and len(runs) == 1 and runs[0].reason == "cancelled"
    assert_owned_cleanup(runs, roots)
