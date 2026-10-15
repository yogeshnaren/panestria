"""Separate processes cannot load a second owner-managed primary model."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from panestria.contracts.inference import InferenceUnavailable
from panestria.resources.primary import PrimaryLease


def test_primary_shared_across_processes_and_release(tmp_path: Path) -> None:
    location = tmp_path / "private"
    first, second = PrimaryLease(location), PrimaryLease(location)
    first.acquire()
    with pytest.raises(InferenceUnavailable, match="primary_in_use"):
        second.acquire()
    code = """
import sys
from pathlib import Path
from panestria.resources.primary import PrimaryLease
from panestria.contracts.inference import InferenceUnavailable
lease=PrimaryLease(Path(sys.argv[1]))
try: lease.acquire()
except InferenceUnavailable as error:
 print(error.code)
else:
 lease.release();sys.exit(1)
"""
    result = subprocess.run([sys.executable, "-c", code, str(location)], capture_output=True, text=True, timeout=5)
    assert result.returncode == 0 and result.stdout.strip() == "primary_in_use"
    first.release()
    second.acquire()
    second.release()
    assert location.stat().st_mode & 0o077 == 0
