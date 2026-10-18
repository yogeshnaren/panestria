"""Real JavaScript execution; deterministic DOM/fetch seams are not browser conformance."""

import shutil
import subprocess
from pathlib import Path

import pytest


def test_packaged_ask_session_lifecycle(record_property):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for JavaScript seam checks; browser acceptance remains pending")
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [node, str(root / "tests/fixtures/ask_session_checks.cjs"), str(root / "src/panestria/api/assets/ask.js")],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "7 session scenarios passed\n"
    record_property(
        "scope", "actual Node execution with deterministic DOM/HTTP seams; not real browser or release proof"
    )
