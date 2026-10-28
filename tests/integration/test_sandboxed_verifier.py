"""A reviewed verifier cannot inherit host secrets or escape its readonly candidate."""

from __future__ import annotations

from pathlib import Path

import pytest

from panestria.verification.registry import CommandRegistry
from panestria.verification.sandboxed import SandboxedCheckRunner


@pytest.mark.docker_boundary
@pytest.mark.live
def test_verifier_os_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = tmp_path / "candidates" / "one"
    workspace.mkdir(parents=True)
    (workspace / "answer.txt").write_text("verified")
    bundle = tmp_path / "protected"
    bundle.mkdir()
    script = bundle / "required_check.py"
    script.write_text("""
import os,socket
from pathlib import Path
assert not os.environ.get('OPENAI_API_KEY')
assert Path(os.environ['PANESTRIA_CANDIDATE'],'answer.txt').read_text()=='verified'
try: Path('/workspace/poison.txt').write_text('unauthorized')
except OSError: pass
else: raise AssertionError('candidate writable')
try: socket.socket(socket.AF_INET,socket.SOCK_STREAM)
except PermissionError: pass
else: raise AssertionError('public socket accessible')
print('independent_check_passed')
""")
    monkeypatch.setenv("OPENAI_API_KEY", "SYNTHETIC_HOST_SECRET_SENTINEL")
    registry = CommandRegistry.load(bundle, "/synthetic/registered-python")
    runner = SandboxedCheckRunner(registry, workspace.parent)
    result = runner.run("synthetic-required", workspace, 10.0)
    assert result.verdict == "PASS" and b"independent_check_passed" in result.output
    assert b"SYNTHETIC_HOST_SECRET_SENTINEL" not in result.output and not (workspace / "poison.txt").exists()
    assert runner.run("worker-invented-command", workspace, 10.0).reason == "unregistered_command"
    script.write_text("raise SystemExit(0) # corrupted bundle")
    assert runner.run("synthetic-required", workspace, 10.0).reason == "bundle_tampered"
