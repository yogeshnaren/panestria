"""AOS-001-TC02. Toolchain gates fail on disposable fixtures and pass on this tree."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = ROOT / "tests" / "fixtures" / "boundaries" / "forbidden"
ALLOWED = ROOT / "tests" / "fixtures" / "boundaries" / "allowed"
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


def test_installed_package_imports() -> None:
    completed = _run([sys.executable, "-c", "import panestria, panestria.config, panestria.api, panestria.cli"])
    assert completed.returncode == 0, completed.stderr


def test_production_import_boundary_passes() -> None:
    completed = _run(["uv", "run", "--frozen", "lint-imports", "--config", ".importlinter"])
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_forbidden_import_fails_boundary_gate() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(FORBIDDEN)
    completed = _run(
        ["uv", "run", "--frozen", "lint-imports", "--config", str(FORBIDDEN / ".importlinter")],
        env=env,
    )
    assert completed.returncode != 0
    assert "badpkg.domain" in completed.stdout + completed.stderr


def test_allowed_import_passes_boundary_gate() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ALLOWED)
    completed = _run(
        ["uv", "run", "--frozen", "lint-imports", "--config", str(ALLOWED / ".importlinter")],
        env=env,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_current_lock_matches_metadata() -> None:
    completed = _run(["uv", "lock", "--check", "--offline"])
    assert completed.returncode == 0, completed.stderr


def test_stale_lock_fails(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    text = text.replace('dependencies = [', 'dependencies = [\n  "packaging>=23",', 1)
    (project / "pyproject.toml").write_text(text, encoding="utf-8")
    (project / "uv.lock").write_text((ROOT / "uv.lock").read_text(encoding="utf-8"), encoding="utf-8")
    completed = _run(["uv", "lock", "--check", "--offline"], cwd=project)
    assert completed.returncode != 0


def test_production_lint_and_types_pass() -> None:
    lint = _run(["uv", "run", "--frozen", "ruff", "check", "."])
    types = _run(["uv", "run", "--frozen", "mypy", "src/panestria"])
    assert lint.returncode == 0, lint.stdout + lint.stderr
    assert types.returncode == 0, types.stdout + types.stderr


def test_disposable_lint_and_type_failures(tmp_path: Path) -> None:
    unused = tmp_path / "unused_import.py"
    unused.write_text("import os\n", encoding="utf-8")
    lint = _run(["uv", "run", "--frozen", "ruff", "check", str(unused)])
    assert lint.returncode != 0
    mismatch = tmp_path / "bad_type.py"
    mismatch.write_text("value: int = 'synthetic'\n", encoding="utf-8")
    types = _run(["uv", "run", "--frozen", "mypy", "--strict", str(mismatch)])
    assert types.returncode != 0


def test_disposable_failing_unit_test(tmp_path: Path) -> None:
    target = tmp_path / "test_fail.py"
    target.write_text("def test_fail() -> None:\n    assert False\n", encoding="utf-8")
    completed = _run(["uv", "run", "--frozen", "pytest", "-p", "no:cacheprovider", str(target)])
    assert completed.returncode != 0


def test_repository_secret_scan_passes_and_sentinel_fails() -> None:
    clean = _run(["uv", "run", "--frozen", "python", "tools/secret_scan.py"])
    dirty = _run(["uv", "run", "--frozen", "python", "tools/secret_scan.py", str(SENTINEL)])
    assert clean.returncode == 0, clean.stdout
    assert dirty.returncode != 0
    assert dirty.stdout.strip() == "tests/fixtures/boundaries/secret_sentinel.txt: aws-access-key-id"


def test_ci_does_not_inject_provider_credentials() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    for name in PROVIDER_NAMES:
        assert name not in workflow
    assert "secrets." not in workflow


def test_make_bootstrap_uses_the_frozen_cache() -> None:
    env = os.environ.copy()
    env["UV_OFFLINE"] = "1"
    completed = _run(["make", "bootstrap"], env=env)
    assert completed.returncode == 0, completed.stderr


def test_make_test_excludes_the_live_case() -> None:
    completed = _run(["make", "-n", "test"])
    assert completed.returncode == 0, completed.stderr
    assert 'pytest -m "not live"' in completed.stdout


def test_reset_rejects_an_extra_path() -> None:
    completed = _run(["make", "reset-synthetic-data", "/tmp"])
    assert completed.returncode != 0
    assert "unsupported_target" in completed.stderr
    assert "panestria_s3_pgdata" not in completed.stdout + completed.stderr


def test_dev_api_rejects_a_non_loopback_bind() -> None:
    env = os.environ.copy()
    env["PANESTRIA_BIND_HOST"] = "0.0.0.0"
    completed = _run(["make", "dev-api"], env=env)
    text = completed.stdout + completed.stderr
    assert completed.returncode == 2
    assert "invalid_bind" in text
    assert "placeholder-not-a-secret" not in text
    assert "55432" not in text
