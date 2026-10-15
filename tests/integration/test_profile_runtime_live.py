"""Actual OS secrets + constrained model + scoped HTTP; no mock provider/key."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

import pytest
from test_ask_kernel import initialize

from panestria.contracts.inference import InferenceUnavailable
from panestria.inference.runtime import ModelRuntime


class PreservingQualificationRuntime(ModelRuntime):
    def _reap_orphans(self) -> None:
        # Preserve every pre-existing controller/container, including stale ones.
        # All actual model startup/isolation/provider behavior stays unchanged.
        if self._docker(["ps", "-a", "-q", "--filter", "label=panestria.purpose=local-model"]).strip():
            raise InferenceUnavailable("existing_model_service_preserved")


@pytest.mark.live
def test_actual_profile_runtime_boundary(r1_task, tmp_path, record_property):
    bus, daemon = shutil.which("dbus-run-session"), shutil.which("gnome-keyring-daemon")
    if sys.platform != "linux" or not bus or not daemon:
        pytest.skip("actual Linux Secret Service prerequisites missing; not qualified")
    # Explicit public model cache input; never download or modify owner assets.
    cache_value = os.environ.get("PANESTRIA_PROFILE_TEST_MODEL_CACHE")
    if not cache_value:
        pytest.skip("explicit read-only local model cache not provided; not qualified")
    initialize(r1_task, tmp_path)
    private = tmp_path / "os-session"
    private.mkdir(mode=0o700)
    environment = {name: os.environ[name] for name in ("PATH", "LANG", "LD_LIBRARY_PATH") if name in os.environ}
    for name, directory in (("XDG_DATA_HOME", "data"), ("XDG_CONFIG_HOME", "config"), ("XDG_RUNTIME_DIR", "runtime")):
        path = private / directory
        path.mkdir(mode=0o700)
        environment[name] = str(path)
    (private / "control").mkdir(mode=0o700)
    environment["PANESTRIA_ISOLATED_KEYRING"] = str(private)
    model = PreservingQualificationRuntime(Path(cache_value), tmp_path / "model-socket", gpu=False)
    # Refuse to reap even stale resources during this test: preserve other runs.
    existing = model._docker(["ps", "-a", "-q", "--filter", "label=panestria.purpose=local-model"]).strip()
    assert not existing, "existing_model_service_preserved; actual qualification not run"
    try:
        model.start()
        actual = model.effective
        assert actual["HostConfig"]["NetworkMode"] == "none" and not actual["HostConfig"]["PortBindings"]
        destinations = {mount["Destination"] for mount in actual["Mounts"]}
        assert destinations == {
            "/usr/local/bin/ollama",
            "/usr/local/lib/ollama",
            "/models",
            "/bridge",
            "/runtime/bridge.py",
        }
        assert all(not mount["RW"] for mount in actual["Mounts"] if mount["Destination"] != "/bridge")
        assert not any(
            "DBUS_SESSION_BUS_ADDRESS=" in value or "PANESTRIA_DATABASE_URL=" in value
            for value in actual["Config"]["Env"]
        )
        script = Path(__file__).resolve().parents[1] / "fixtures/profile_runtime_probe.py"
        process = subprocess.Popen(
            [
                bus,
                "--",
                sys.executable,
                str(script),
                str(private),
                daemon,
                r1_task["dsn"],
                r1_task["owner"],
                r1_task["project"],
                str(model.socket_path),
            ],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=85)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=3)
            pytest.fail("actual profile runtime deadline exceeded")
        assert process.returncode == 0, "actual profile runtime failed: " + stderr.decode()
        report = json.loads(stdout)
        assert report["status"] == "PASS" and report["model_calls"] == 1
        assert report["actual_os_store"] and report["actual_local_model"]
        record_property("execution_mode", "ACTUAL_ISOLATED_OS_STORE_LOCAL_MODEL_ASGI_HTTP")
        record_property("runtime_network", "none")
        record_property("runtime_mounts_exclude_os_store_database_home", True)
        record_property("preexisting_model_resources", "preserved; orphan recovery is not qualified here")
        record_property("qualification_scope", "synthetic component; owner trial and full privacy cases not claimed")
    finally:
        model.stop()
