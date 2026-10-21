"""Actual isolated OS secrets + supported CPU service lifecycle/physical HTTP."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from panestria.inference.runtime import ModelRuntime


@pytest.mark.live
def test_actual_profile_runtime_boundary(r1_database, tmp_path, record_property):
    bus, daemon = shutil.which("dbus-run-session"), shutil.which("gnome-keyring-daemon")
    if sys.platform != "linux" or not bus or not daemon:
        pytest.skip("actual Linux Secret Service prerequisites missing; not qualified")
    cache_value = os.environ.get("PANESTRIA_PROFILE_TEST_MODEL_CACHE")
    if not cache_value:
        pytest.skip("explicit read-only local model cache not provided; not qualified")
    private = tmp_path / "os-session"
    private.mkdir(mode=0o700)
    environment = {name: os.environ[name] for name in ("PATH", "LANG", "LD_LIBRARY_PATH", "HOME") if name in os.environ}
    for name, directory in (("XDG_DATA_HOME", "data"), ("XDG_CONFIG_HOME", "config"), ("XDG_RUNTIME_DIR", "runtime")):
        path = private / directory
        path.mkdir(mode=0o700)
        environment[name] = str(path)
    (private / "control").mkdir(mode=0o700)
    environment["PANESTRIA_ISOLATED_KEYRING"] = str(private)
    model = ModelRuntime(Path(cache_value), tmp_path / "unused-model-socket", preserve_existing=True)
    assert not model._docker(["ps", "-a", "-q", "--filter", "label=panestria.purpose=local-model"]).strip(), (
        "existing_model_service_preserved; actual qualification not run"
    )
    script = Path(__file__).resolve().parents[1] / "fixtures/profile_runtime_probe.py"
    process = subprocess.Popen(
        [bus, "--", sys.executable, str(script), str(private), daemon, r1_database, cache_value],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=150)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGINT)
        try:
            process.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=3)
        pytest.fail("actual profile runtime deadline exceeded; qualification denied; inspect owned cleanup")
    assert process.returncode == 0, "actual profile runtime failed: " + stderr.decode()
    report = json.loads(stdout)
    assert report == {
        "status": "PASS",
        "model_calls": 1,
        "actual_os_store": True,
        "actual_local_model": True,
        "physical_loopback_http": True,
        "owned_model_cleanup": True,
    }
    record_property("execution_mode", "ACTUAL_ISOLATED_OS_STORE_LOCAL_MODEL_LOOPBACK_HTTP")
    record_property("runtime_network", "none")
    record_property("runtime_mounts_exclude_os_store_database_home", True)
    record_property("preexisting_model_resources", "preserved; orphan recovery is not qualified here")
    record_property("qualification_scope", "synthetic boundary; owner trial/model style quality not claimed")
