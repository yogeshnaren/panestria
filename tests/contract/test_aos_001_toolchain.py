"""Retained developer-entrypoint safety and the repository's secret scanner.

CI runs lock/lint/types/import boundaries once. Testing those third-party tools
again, installing the project inside pytest, and asserting CI's command spelling
are historical bootstrap checks, not application regressions.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SENTINEL = ROOT / "tests" / "fixtures" / "boundaries" / "secret_sentinel.txt"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
PROVIDER_NAMES = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "GEMINI_API_KEY",
)


def _run(argv: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.fixture(autouse=True)
def _case_metadata(record_property: pytest.RecordProperty) -> None:
    commit = _run(["git", "rev-parse", "HEAD"]).stdout.strip()
    dirty = bool(_run(["git", "status", "--porcelain"]).stdout.strip())
    digest = hashlib.sha256(SENTINEL.read_bytes()).hexdigest()
    record_property("gate_case_id", "AOS-001-TC02")
    record_property("candidate_commit", commit)
    record_property("fixture_digest", digest)
    record_property("lane", "contract")
    record_property("execution_mode", "HERMETIC")
    record_property("worktree_state", "dirty" if dirty else "clean")


def test_repository_secret_scanner_rejects_sentinel_without_printing_secret() -> None:
    dirty = _run(["uv", "run", "--frozen", "python", "tools/secret_scan.py", str(SENTINEL)])
    assert dirty.returncode != 0
    assert dirty.stdout.strip() == "tests/fixtures/boundaries/secret_sentinel.txt: aws-access-key-id"


def test_ci_does_not_inject_provider_credentials() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "pull_request_target" not in workflow
    for name in PROVIDER_NAMES:
        assert name not in workflow
    assert "secrets." not in workflow


def test_reset_rejects_an_extra_path() -> None:
    completed = _run(["make", "reset-synthetic-data", "/tmp"])
    assert completed.returncode != 0
    assert "unsupported_target" in completed.stderr
    assert "panestria_s3_pgdata" not in completed.stdout + completed.stderr


def test_r0_demo_rejects_a_non_loopback_bind() -> None:
    env = os.environ.copy()
    env["PANESTRIA_BIND_HOST"] = "0.0.0.0"
    completed = _run(["make", "r0-demo"], env=env)
    text = completed.stdout + completed.stderr
    assert completed.returncode != 0
    assert "invalid_bind" in text
    assert "placeholder-not-a-secret" not in text
    assert "55432" not in text


def test_dev_api_rejects_a_non_loopback_bind() -> None:
    env = os.environ.copy()
    env["PANESTRIA_BIND_HOST"] = "0.0.0.0"
    completed = _run(["make", "dev-api"], env=env)
    text = completed.stdout + completed.stderr
    assert completed.returncode == 2
    assert "invalid_bind" in text
    assert "placeholder-not-a-secret" not in text
    assert "55432" not in text
