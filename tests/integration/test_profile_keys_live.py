"""Synthetic keys on an actual isolated OS bus; never use the owner keyring."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.live
@pytest.mark.skipif(sys.platform != "linux", reason="Linux Secret Service qualification")
def test_isolated_secret_service_backend(tmp_path: Path, record_property: pytest.RecordProperty) -> None:
    bus = shutil.which("dbus-run-session")
    daemon = shutil.which("gnome-keyring-daemon")
    if not bus or not daemon:
        pytest.skip("actual isolated Secret Service tools unavailable; not qualified")
    tmp_path.chmod(0o700)
    environment = {name: os.environ[name] for name in ("PATH", "LANG", "LD_LIBRARY_PATH") if name in os.environ}
    for name, directory in (("XDG_DATA_HOME", "data"), ("XDG_CONFIG_HOME", "config"), ("XDG_RUNTIME_DIR", "runtime")):
        path = tmp_path / directory
        path.mkdir(mode=0o700)
        environment[name] = str(path)
    (tmp_path / "control").mkdir(mode=0o700)
    environment["PANESTRIA_ISOLATED_KEYRING"] = str(tmp_path)
    # No inherited desktop bus, display, keyring socket, auth or profile variables.
    script = Path(__file__).resolve().parents[1] / "fixtures/profile_keyring_probe.py"
    process = subprocess.Popen(
        [bus, "--", sys.executable, str(script), str(tmp_path), daemon],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=35)
    except subprocess.TimeoutExpired:
        # Only this newly created child group contains the disposable bus/daemon.
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate(timeout=3)
        pytest.fail("isolated Secret Service qualification deadline exceeded")
    assert process.returncode == 0, "isolated Secret Service qualification failed: " + stderr.decode()
    assert json.loads(stdout) == {
        "status": "PASS",
        "scopes": 4,
        "persistent_test_keyring": True,
        "locked_denied": True,
        "daemon_restart_preserved_keys": True,
    }
    record_property("execution_mode", "ACTUAL_ISOLATED_OS_SECRET_SERVICE")
    record_property("qualification_scope", "profile-key-backend-only; full-vault-case-not-claimed")
