"""AOS-001-TC01. Several unit tests map to this one scenario group.

Permanent checks cover installation, profile rejection, safe health output,
and the readiness deadline. They do not forbid later packages or routes.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import inspect
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import get_type_hints

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from typer.testing import CliRunner

from panestria import package_version
from panestria.api.health import (
    PROBE_SHUTDOWN_BUDGET_SECONDS,
    DependencyCheck,
    HealthService,
    Liveness,
    ProbeCheck,
    ProbeObservation,
    Readiness,
)
from panestria.api.main import create_app
from panestria.cli.main import app as cli_app
from panestria.config import PUBLIC_HEALTH_REASONS, ProfileRejected, Settings, ValidatedSettings, load_settings

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "aos001_synthetic_dev.json"
FIXTURE = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
BASELINE = "4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917"
ENV_NAMES = (
    "PANESTRIA_SCHEMA_VERSION",
    "PANESTRIA_PROFILE",
    "PANESTRIA_BIND_HOST",
    "PANESTRIA_BIND_PORT",
    "PANESTRIA_READINESS_BUDGET_MS",
    "PANESTRIA_DATABASE_URL",
)
PROVIDER_KEYS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "GEMINI_API_KEY",
)
HYPHEN_SENTINEL = "synthetic-dev-sentinel"
VALID_URLS = (
    "postgresql://panestria_synthetic:syntheticdevsentinel@127.0.0.1:5432/panestria_synthetic",
    "postgresql://panestria_synthetic:syntheticdevsentinel@127.0.0.1/panestria_synthetic",
    "postgresql://panestria_synthetic:syntheticdevsentinel@[::1]:5432/panestria_synthetic",
    "postgresql://panestria_synthetic:syntheticdevsentinel@[::1]/panestria_synthetic",
    "postgresql+psycopg://panestria_synthetic:syntheticdevsentinel@db/panestria_synthetic",
    "postgresql://panestria_synthetic:placeholder-not-a-secret@127.0.0.1:5432/panestria_synthetic",
)
INVALID_URLS = (
    "postgresql://user:syntheticsecret@[broken/db",
    "postgresql://user:syntheticsecret@127.0.0.1:banana/db",
    "postgresql://user:syntheticsecret@127.0.0.1:99999/db",
    "postgresql://user:syntheticsecret@127.0.0.1:0/db",
    "sqlite:///panestria.db",
    "postgresql://panestria_synthetic@127.0.0.1:5432/panestria_synthetic",
    "postgresql://panestria_synthetic:shortpw@127.0.0.1:5432/panestria_synthetic",
    "postgresql://panestria_synthetic:not_probed@127.0.0.1:5432/panestria_synthetic",
    "postgresql://panestria_synthetic:syntheticdevsentinel@127.0.0.1:5432/panestria_synthetic?sslmode=disable",
    "postgresql://panestria_synthetic:syntheticdevsentinel @127.0.0.1:5432/panestria_synthetic",
)


def _database_url(password: str) -> str:
    return (
        f"postgresql://{FIXTURE['database_user']}:{password}"
        f"@127.0.0.1:5432/{FIXTURE['database_name']}"
    )


def _settings(**overrides: object) -> Settings:
    payload: dict[str, object] = {
        "schema_version": FIXTURE["schema_version"],
        "profile": FIXTURE["profile"],
        "bind_host": FIXTURE["bind_host"],
        "bind_port": FIXTURE["bind_port"],
        "readiness_budget_ms": FIXTURE["readiness_budget_ms"],
        "database_url": _database_url(str(FIXTURE["secret_sentinel"])),
    }
    payload.update(overrides)
    return Settings.model_validate(payload)


def _validated(**overrides: object) -> ValidatedSettings:
    return _settings(**overrides).validate_profile()


def _unavailable(reason: str) -> Callable[[datetime], ProbeObservation]:
    def probe(deadline: datetime) -> ProbeObservation:
        del deadline
        return ProbeObservation(
            checks=[ProbeCheck(name="database", status="unavailable", reason=reason)]
        )

    return probe


def _future(seconds: float = 1.0) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


def _child_pids() -> list[int]:
    proc = subprocess.Popen(
        ["ps", "-o", "pid=", "--ppid", str(os.getpid())],
        stdout=subprocess.PIPE,
        text=True,
    )
    output, _error = proc.communicate()
    return [int(part) for part in output.split() if part.strip() and int(part) != proc.pid]


@contextmanager
def _service(probe: Callable[[datetime], ProbeObservation], **overrides: object) -> Iterator[HealthService]:
    service = HealthService(_validated(**overrides), probe)
    try:
        yield service
    finally:
        service.shutdown()


@pytest.fixture(autouse=True)
def _case_metadata(
    request: pytest.FixtureRequest,
    record_property: Callable[[str, object], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if request.node.name == "test_fresh_host_loopback":
        return
    for key in list(os.environ):
        if key.startswith("PANESTRIA_") or key in PROVIDER_KEYS:
            monkeypatch.delenv(key, raising=False)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
    record_property("gate_case_id", "AOS-001-TC01")
    record_property("candidate_commit", commit)
    record_property("fixture_digest", hashlib.sha256(FIXTURE_PATH.read_bytes()).hexdigest())
    record_property("lane", "unit")
    record_property("execution_mode", "HERMETIC")
    record_property("worktree_state", "dirty" if dirty else "clean")


@pytest.mark.unit
def test_package_install_and_preserved_license() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["name"] == "panestria"
    assert project["license"] == "MIT"
    assert project["requires-python"] == ">=3.12"
    assert project["scripts"]["panestria"] == "panestria.cli.main:app"
    assert "agentos" not in json.dumps(project)
    assert 'name = "panestria"' in (ROOT / "uv.lock").read_text(encoding="utf-8")
    assert importlib.util.find_spec("agentos") is None
    import panestria

    assert Path(panestria.__file__).resolve() == (ROOT / "src" / "panestria" / "__init__.py").resolve()
    assert package_version() == importlib.metadata.version("panestria")
    license_now = (ROOT / "LICENSE").read_bytes()
    license_baseline = subprocess.check_output(["git", "show", f"{BASELINE}:LICENSE"], cwd=ROOT)
    assert license_now == license_baseline
    source = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "src").rglob("*.py"))
    assert "pip install" not in source
    assert list(inspect.signature(create_app).parameters) == ["settings", "readiness_probe"]
    assert get_type_hints(create_app)["return"].__name__ == "FastAPI"
    assert get_type_hints(Settings.validate_profile)["return"] is ValidatedSettings
    assert get_type_hints(HealthService.readiness)["return"] is Readiness
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    for name in ENV_NAMES:
        assert name in example
    assert "sk-" not in example
    assert "127.0.0.1:55432" in example


@pytest.mark.unit
def test_contributor_and_security_notes_have_no_secrets() -> None:
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    for text in (contributing, security):
        assert "docs/phase-tracker.json" in text
        assert "sk-" not in text
        assert "AKIA" not in text
        assert "BEGIN PRIVATE KEY" not in text
    assert "make test" in contributing
    assert "127.0.0.1" in security


@pytest.mark.unit
def test_local_environment_files_are_ignored() -> None:
    def ignored(path: str) -> bool:
        completed = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT, check=False)
        return completed.returncode == 0

    assert ignored(".env")
    assert ignored(".env.local")
    assert ignored("dist/panestria.whl")
    assert ignored("build/lib/panestria.py")
    assert not ignored(".env.example")
    assert not ignored("uv.lock")
    assert not ignored("tests/fixtures/aos001_synthetic_dev.json")
    assert not ignored("evidence/AOS-001.xml")


@pytest.mark.unit
@pytest.mark.parametrize("host", FIXTURE["loopback_hosts"])
def test_loopback_bind_accepted(host: str) -> None:
    assert _validated(bind_host=host).bind_host == host


@pytest.mark.unit
@pytest.mark.parametrize("host", FIXTURE["invalid_bind_hosts"])
def test_invalid_bind_rejected(host: str) -> None:
    sentinel = str(FIXTURE["secret_sentinel"])
    with pytest.raises(ProfileRejected) as rejected:
        _validated(bind_host=host)
    assert rejected.value.code == "invalid_bind"
    assert sentinel not in rejected.value.message
    if host:
        assert str(host) not in rejected.value.message


@pytest.mark.unit
def test_direct_non_loopback_settings_are_unrepresentable() -> None:
    sentinel = str(FIXTURE["secret_sentinel"])
    with pytest.raises(ValidationError) as rejected:
        ValidatedSettings(
            schema_version=1,
            profile="SYNTHETIC_DEV",
            bind_host="0.0.0.0",
            bind_port=8765,
            readiness_budget_ms=500,
            database_url=SecretStr(_database_url(sentinel)),
        )
    assert sentinel not in str(rejected.value)


@pytest.mark.unit
@pytest.mark.parametrize("profile", FIXTURE["rejected_profiles"])
def test_disabled_profiles_rejected(profile: str) -> None:
    with pytest.raises(ProfileRejected) as rejected:
        _validated(profile=profile)
    assert rejected.value.code == "invalid_profile"


@pytest.mark.unit
@pytest.mark.parametrize("port", FIXTURE["invalid_ports"])
def test_invalid_bind_port_rejected(port: int) -> None:
    with pytest.raises(ProfileRejected) as rejected:
        _validated(bind_port=port)
    assert rejected.value.code == "invalid_bind"


@pytest.mark.unit
def test_schema_bool_and_budget_rejected() -> None:
    with pytest.raises(ProfileRejected) as bad_version:
        _validated(schema_version=2)
    assert bad_version.value.code == "invalid_schema_version"
    with pytest.raises(ValidationError):
        _settings(schema_version=True)
    with pytest.raises(ValidationError):
        _settings(bind_port=True)
    with pytest.raises(ValidationError):
        _settings(readiness_budget_ms=1.5)
    with pytest.raises(ProfileRejected) as short_budget:
        _validated(readiness_budget_ms=10)
    assert short_budget.value.code == "invalid_settings"


@pytest.mark.unit
@pytest.mark.parametrize("url", VALID_URLS)
def test_documented_database_urls_accepted(url: str) -> None:
    validated = _validated(database_url=url)
    assert validated.database_url.get_secret_value() == url
    assert url not in validated.model_dump_json()


@pytest.mark.unit
@pytest.mark.parametrize("url", INVALID_URLS)
def test_malformed_database_urls_rejected(url: str) -> None:
    with pytest.raises(ProfileRejected) as rejected:
        _validated(database_url=url)
    assert rejected.value.code == "invalid_database_url"
    assert url not in rejected.value.message
    assert "syntheticsecret" not in rejected.value.message
    assert "syntheticdevsentinel" not in rejected.value.message
    assert "Traceback" not in rejected.value.message


@pytest.mark.unit
def test_unknown_environment_names_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = str(FIXTURE["secret_sentinel"])
    monkeypatch.setenv("PANESTRIA_SCHEMA_VERSION", "1")
    monkeypatch.setenv("PANESTRIA_PROFILE", "SYNTHETIC_DEV")
    monkeypatch.setenv("PANESTRIA_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("PANESTRIA_BIND_PORT", "8765")
    monkeypatch.setenv("PANESTRIA_READINESS_BUDGET_MS", "500")
    monkeypatch.setenv("PANESTRIA_DATABASE_URL", _database_url(sentinel))
    monkeypatch.setenv("PANESTRIA_API_TOKEN", sentinel)
    with pytest.raises(ProfileRejected) as extra:
        load_settings()
    assert extra.value.code == "invalid_settings"
    assert sentinel not in extra.value.message


@pytest.mark.unit
def test_healthz_does_not_probe(tmp_path: Path) -> None:
    marker = tmp_path / "probed"
    version = package_version()

    def explode(deadline: datetime) -> ProbeObservation:
        marker.write_text("called")
        raise AssertionError(f"liveness must not probe {deadline}")

    with TestClient(create_app(_validated(), explode)) as client:
        live = client.get("/healthz")
        schema = client.get("/openapi.json")
    assert not marker.exists()
    assert live.status_code == 200
    assert live.json() == {
        "schema_version": 1,
        "status": "live",
        "version": version,
        "profile": "SYNTHETIC_DEV",
    }
    assert live.json()["version"] == version
    assert "access-control-allow-origin" not in {key.lower() for key in live.headers}
    document = schema.json()
    assert "/healthz" in document["paths"]
    assert "/readyz" in document["paths"]
    encoded = json.dumps(document)
    assert "Liveness" in encoded or "live" in encoded
    assert str(FIXTURE["secret_sentinel"]) not in encoded
    assert "database_url" not in encoded
    hints = get_type_hints(Liveness)
    assert set(hints) >= {"schema_version", "status", "version", "profile"}
    readiness_fields = set(get_type_hints(Readiness))
    assert readiness_fields >= {"schema_version", "status", "checks"}
    assert set(get_type_hints(DependencyCheck)) >= {"name", "status", "reason"}


@pytest.mark.unit
def test_unavailable_database_is_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = str(FIXTURE["secret_sentinel"])
    provider = str(FIXTURE["provider_sentinel"])
    monkeypatch.setenv("OPENAI_API_KEY", provider)
    monkeypatch.setenv("ANTHROPIC_API_KEY", provider)
    validated = _validated()
    with TestClient(create_app(validated, _unavailable("database_unavailable"))) as client:
        ready = client.get("/readyz")
    assert ready.status_code == 503
    assert ready.json() == {
        "schema_version": 1,
        "status": "not_ready",
        "checks": [
            {"name": "database", "status": "unavailable", "reason": "database_unavailable"},
            {"name": "executor", "status": "not_configured", "reason": "not_implemented"},
        ],
    }
    assert sentinel not in ready.text
    assert provider not in ready.text
    assert "postgresql://" not in ready.text


@pytest.mark.unit
def test_degraded_database_stays_unready_executor() -> None:
    def degraded(deadline: datetime) -> ProbeObservation:
        del deadline
        return ProbeObservation(
            checks=[ProbeCheck(name="database", status="degraded", reason="capacity_unknown")]
        )

    with _service(degraded) as service:
        body = service.readiness(_future())
    assert body.status == "degraded"
    assert body.checks[0].status == "degraded"
    assert body.checks[1].status == "not_configured"
    assert body.checks[1].reason == "not_implemented"


@pytest.mark.unit
def test_executor_ready_claim_is_ignored() -> None:
    def lying(deadline: datetime) -> ProbeObservation:
        del deadline
        return ProbeObservation(
            checks=[
                ProbeCheck(name="database", status="ready", reason="ready"),
                ProbeCheck(name="executor", status="ready", reason="ready"),
            ]
        )

    with _service(lying) as service:
        body = service.readiness(_future())
    assert body.status == "not_ready"
    assert body.checks[0].status == "ready"
    assert body.checks[1].status == "not_configured"


@pytest.mark.unit
def test_duplicate_database_check_is_probe_failed() -> None:
    def duplicate(deadline: datetime) -> ProbeObservation:
        del deadline
        return ProbeObservation(
            checks=[
                ProbeCheck(name="database", status="ready", reason="ready"),
                ProbeCheck(name="database", status="unavailable", reason="database_unavailable"),
            ]
        )

    with _service(duplicate) as service:
        body = service.readiness(_future())
    assert body.checks[0].reason == "probe_failed"


@pytest.mark.unit
def test_expired_deadline_does_not_invoke_probe(tmp_path: Path) -> None:
    marker = tmp_path / "called"

    def probe(deadline: datetime) -> ProbeObservation:
        marker.write_text(deadline.isoformat())
        return _unavailable("database_unavailable")(deadline)

    with _service(probe) as service:
        body = service.readiness(datetime.now(timezone.utc) - timedelta(seconds=5))
        with pytest.raises(ProfileRejected) as naive:
            service.readiness(datetime.now())
    assert not marker.exists()
    assert body.checks[0].reason == "deadline_exceeded"
    assert naive.value.code == "invalid_deadline"


@pytest.mark.unit
def test_repeated_timeouts_keep_workers_bounded(tmp_path: Path) -> None:
    finished = tmp_path / "finished"

    def block(deadline: datetime) -> ProbeObservation:
        del deadline
        time.sleep(30)
        finished.write_text("late")
        return _unavailable("database_unavailable")(datetime.now(timezone.utc))

    threads_before = threading.active_count()
    with _service(block, readiness_budget_ms=50) as service:
        for _ in range(12):
            started = time.monotonic()
            body = service.readiness(datetime.now(timezone.utc) + timedelta(milliseconds=10))
            elapsed = time.monotonic() - started
            assert body.checks[0].reason == "deadline_exceeded"
            assert elapsed < 0.05 + PROBE_SHUTDOWN_BUDGET_SECONDS
            assert _child_pids() == []
        assert threading.active_count() == threads_before
        started = time.monotonic()
        service.shutdown()
        assert time.monotonic() - started <= PROBE_SHUTDOWN_BUDGET_SECONDS
    assert not finished.exists()
    assert threading.active_count() == threads_before


@pytest.mark.unit
def test_second_poll_does_not_queue_another_probe(tmp_path: Path) -> None:
    marker = tmp_path / "entered"

    def block(deadline: datetime) -> ProbeObservation:
        del deadline
        marker.write_text("entered")
        time.sleep(30)
        return _unavailable("database_unavailable")(datetime.now(timezone.utc))

    first: dict[str, object] = {}

    def run(service: HealthService) -> None:
        first["body"] = service.readiness(_future(5))

    with _service(block) as service:
        worker = threading.Thread(target=run, args=(service,))
        worker.start()
        for _ in range(50):
            if marker.exists():
                break
            time.sleep(0.02)
        assert marker.exists()
        started = time.monotonic()
        busy = service.readiness(_future(1))
        assert time.monotonic() - started < 0.5
        assert busy.checks[0].reason == "probe_busy"
        assert len(_child_pids()) == 1
        shutdown_started = time.monotonic()
        service.shutdown()
        assert time.monotonic() - shutdown_started <= PROBE_SHUTDOWN_BUDGET_SECONDS
        worker.join(PROBE_SHUTDOWN_BUDGET_SECONDS + 0.5)
        assert not worker.is_alive()
    assert isinstance(first["body"], Readiness)


@pytest.mark.unit
def test_interpreter_exits_after_stuck_probe() -> None:
    script = """
import time
from datetime import datetime, timedelta, timezone
from panestria.api.health import HealthService, ProbeCheck, ProbeObservation
from panestria.config import Settings

def block(deadline):
    time.sleep(300)
    return ProbeObservation(checks=[ProbeCheck(name="database", status="ready", reason="ready")])

settings = Settings(
    database_url="postgresql://panestria_synthetic:placeholder-not-a-secret@127.0.0.1:5432/panestria_synthetic"
).validate_profile()
service = HealthService(settings, block)
body = service.readiness(datetime.now(timezone.utc) + timedelta(milliseconds=30))
assert body.checks[0].reason == "deadline_exceeded"
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        check=False,
        timeout=PROBE_SHUTDOWN_BUDGET_SECONDS + 2,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


@pytest.mark.unit
def test_encoded_and_arbitrary_probe_text_are_not_emitted() -> None:
    encoded = "postgresql://user:%73yntheticsecret@127.0.0.1:5432/db"
    validated = _validated(database_url=encoded)
    assert "%73yntheticsecret" in validated.secret_material()
    assert "syntheticsecret" in validated.secret_material()

    def leak(deadline: datetime) -> ProbeObservation:
        del deadline
        return ProbeObservation(
            checks=[ProbeCheck(name="database", status="unavailable", reason="syntheticsecret")]
        )

    with _service(leak, database_url=encoded) as service:
        body = service.readiness(_future())
    text = body.model_dump_json()
    assert "syntheticsecret" not in text
    assert "%73yntheticsecret" not in text
    assert body.checks[0].reason == "probe_failed"

    def hyphen(deadline: datetime) -> ProbeObservation:
        del deadline
        return ProbeObservation(
            checks=[ProbeCheck(name="database", status="unavailable", reason=HYPHEN_SENTINEL)]
        )

    with _service(hyphen) as service:
        hidden = service.readiness(_future())
    assert HYPHEN_SENTINEL not in hidden.model_dump_json()
    assert hidden.checks[0].reason == "probe_failed"

    def blows(deadline: datetime) -> ProbeObservation:
        del deadline
        raise RuntimeError(f"postgresql://user:{HYPHEN_SENTINEL}@127.0.0.1/db")

    with _service(blows) as service:
        failed = service.readiness(_future())
    assert failed.checks[0].reason == "probe_failed"
    assert HYPHEN_SENTINEL not in failed.model_dump_json()
    assert "postgresql://" not in failed.model_dump_json()
    assert set(PUBLIC_HEALTH_REASONS) >= {check.reason for check in failed.checks}


@pytest.mark.unit
def test_cli_reports_safe_configuration_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = str(FIXTURE["secret_sentinel"])
    version = package_version()
    runner = CliRunner()
    monkeypatch.setenv("PANESTRIA_SCHEMA_VERSION", "1")
    monkeypatch.setenv("PANESTRIA_PROFILE", "SYNTHETIC_DEV")
    monkeypatch.setenv("PANESTRIA_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("PANESTRIA_BIND_PORT", "8765")
    monkeypatch.setenv("PANESTRIA_READINESS_BUDGET_MS", "200")
    monkeypatch.setenv("PANESTRIA_DATABASE_URL", _database_url(sentinel))
    monkeypatch.setenv("OPENAI_API_KEY", str(FIXTURE["provider_sentinel"]))

    health = runner.invoke(cli_app, ["health"])
    combined = f"{health.stdout}{health.stderr}"
    assert health.exit_code == 1
    assert sentinel not in combined
    assert "placeholder-not-a-secret" not in combined
    assert "postgresql://" not in combined
    assert json.loads(health.stdout)["checks"][0]["reason"] == "database_unavailable"

    version_result = runner.invoke(cli_app, ["version"])
    assert version_result.exit_code == 0
    assert version_result.stdout.strip() == version
    flagged = runner.invoke(cli_app, ["--version"])
    assert flagged.exit_code == 0
    assert flagged.stdout.strip() == version
    help_result = runner.invoke(cli_app, ["--help"])
    assert help_result.exit_code == 0
    assert "health" in help_result.stdout
    assert "version" in help_result.stdout

    monkeypatch.setenv("PANESTRIA_BIND_HOST", "0.0.0.0")
    invalid_bind = runner.invoke(cli_app, ["health"])
    bind_text = f"{invalid_bind.stdout}{invalid_bind.stderr}"
    assert invalid_bind.exit_code == 2
    assert '"code": "invalid_bind"' in bind_text
    assert sentinel not in bind_text
    assert "Traceback" not in bind_text

    for url in (
        "postgresql://user:syntheticsecret@[broken/db",
        "postgresql://user:syntheticsecret@127.0.0.1:banana/db",
        "postgresql://user:syntheticsecret@127.0.0.1:99999/db",
    ):
        monkeypatch.setenv("PANESTRIA_BIND_HOST", "127.0.0.1")
        monkeypatch.setenv("PANESTRIA_DATABASE_URL", url)
        rejected = runner.invoke(cli_app, ["health"])
        text = f"{rejected.stdout}{rejected.stderr}"
        assert rejected.exit_code == 2
        assert '"code": "invalid_database_url"' in text
        assert "syntheticsecret" not in text
        assert "Traceback" not in text
        assert "ValueError" not in text


_PROVIDER_KEYS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY")
_SMOKE_PORT = 8767


def _tcp_address(raw: str) -> tuple[str, int]:
    address, port_hex = raw.split(":")
    octets = bytes.fromhex(address)
    return ".".join(str(octet) for octet in octets[::-1]), int(port_hex, 16)


def owned_sockets(table: str, fd_targets: list[str]) -> tuple[list[tuple[str, int]], list[str]]:
    """Listen endpoints and non-loopback peers for sockets this process holds."""
    inodes = {
        target.removeprefix("socket:[").removesuffix("]")
        for target in fd_targets
        if target.startswith("socket:[") and target.endswith("]")
    }
    listens: list[tuple[str, int]] = []
    egress: list[str] = []
    for line in table.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 10 or fields[9] not in inodes:
            continue
        local_host, local_port = _tcp_address(fields[1])
        remote_host, _remote_port = _tcp_address(fields[2])
        if fields[3] == "0A":
            listens.append((local_host, local_port))
        elif fields[3] == "01" and remote_host != "127.0.0.1":
            egress.append(remote_host)
    return listens, egress


def fresh_host_attested(report: object, boot_id: str) -> bool:
    """Identity only. Listener, startup, and RSS fields in the file are ignored."""
    if not isinstance(report, dict):
        return False
    return report.get("boot_id") == boot_id and report.get("venv_created_this_boot") is True


def smoke_denial(
    listens: list[tuple[str, int]],
    egress: list[str],
    rss_kb: str,
    startup_seconds: float,
) -> str | None:
    if listens == [] or any(host != "127.0.0.1" for host, _port in listens):
        return "fresh_host_listener_not_loopback"
    if egress:
        return "fresh_host_egress"
    if not rss_kb.isdigit() or int(rss_kb) <= 0:
        return "fresh_host_rss_missing"
    if startup_seconds <= 0:
        return "fresh_host_startup_missing"
    return None


def test_owned_listen_ignores_other_processes_and_rejects_egress() -> None:
    table = (
        "  sl local_address rem_address st tx_queue:rx_queue tr:tm retrnsmt uid timeout inode\n"
        "   0: 0100007F:2235 00000000:0000 0A 00000000:00000000 00:00000000 00000000 0 0 111\n"
        "   1: 00000000:0016 00000000:0000 0A 00000000:00000000 00:00000000 00000000 0 0 222\n"
        "   2: 0100007F:2236 04030201:01BB 01 00000000:00000000 00:00000000 00000000 0 0 333\n"
    )
    listens, egress = owned_sockets(table, ["socket:[111]", "socket:[333]", "pipe:[9]"])
    assert listens == [("127.0.0.1", 8757)]
    assert egress == ["1.2.3.4"]
    assert smoke_denial(listens, egress, "100", 0.2) == "fresh_host_egress"
    assert smoke_denial([("0.0.0.0", 22)], [], "100", 0.2) == "fresh_host_listener_not_loopback"
    assert smoke_denial(listens, [], "", 0.2) == "fresh_host_rss_missing"
    assert smoke_denial(listens, [], "100", 0) == "fresh_host_startup_missing"
    assert smoke_denial(listens, [], "100", 0.2) is None
    assert fresh_host_attested({"boot_id": "abc", "listen": ["0.0.0.0:22"], "startup_seconds": 1}, "abc") is False
    assert fresh_host_attested({"boot_id": "abc", "venv_created_this_boot": True, "rss_kb": "1"}, "abc") is True


def test_this_process_listen_socket_is_attributed() -> None:
    held = socket.socket()
    held.bind(("127.0.0.1", 0))
    held.listen(1)
    try:
        port = held.getsockname()[1]
        listens, _egress = owned_sockets(Path("/proc/net/tcp").read_text(encoding="utf-8"), _fd_targets(os.getpid()))
    finally:
        held.close()
    assert ("127.0.0.1", port) in listens


def _fd_targets(pid: int) -> list[str]:
    found: list[str] = []
    for entry in Path(f"/proc/{pid}/fd").iterdir():
        try:
            found.append(os.readlink(entry))
        except OSError:
            continue
    return found


def _fail_closed(log_path: Path) -> None:
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    code = lines[-1].strip() if lines else ""
    known = {
        "database_unavailable",
        "invalid_bind",
        "invalid_database_url",
        "invalid_settings",
        "missing_token",
    }
    pytest.fail(code if code in known else "fresh_host_server_exited")


def _measure_loopback_smoke() -> tuple[list[tuple[str, int]], list[str], str, float]:
    database_url = os.environ.get("PANESTRIA_DATABASE_URL", "")
    if database_url == "":
        pytest.fail("fresh_host_database_unavailable")
    env = {key: value for key, value in os.environ.items() if not key.startswith("PANESTRIA_")}
    for key in _PROVIDER_KEYS:
        env.pop(key, None)
    env.update(
        {
            "PANESTRIA_DATABASE_URL": database_url,
            "PANESTRIA_TOKEN": "synthetic-loopback-token",
            "PANESTRIA_SCHEMA_VERSION": "1",
            "PANESTRIA_PROFILE": "SYNTHETIC_DEV",
            "PANESTRIA_BIND_HOST": "127.0.0.1",
            "PANESTRIA_BIND_PORT": str(_SMOKE_PORT),
            "PANESTRIA_READINESS_BUDGET_MS": "1000",
        }
    )
    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as directory:
        log_path = Path(directory) / "server.log"
        log = log_path.open("a", encoding="utf-8")
        process = subprocess.Popen(
            [sys.executable, "-m", "panestria.api.serve"],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    log.flush()
                    _fail_closed(log_path)
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{_SMOKE_PORT}/healthz", timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.1)
            else:
                pytest.fail("fresh_host_startup_missing")
            startup = time.perf_counter() - started
            status = Path(f"/proc/{process.pid}/status").read_text(encoding="utf-8").splitlines()
            rss = next((line.split()[1] for line in status if line.startswith("VmRSS:")), "")
            table = Path("/proc/net/tcp").read_text(encoding="utf-8")
            listens, egress = owned_sockets(table, _fd_targets(process.pid))
            if ("127.0.0.1", _SMOKE_PORT) not in listens:
                pytest.fail("fresh_host_listener_not_loopback")
            return listens, egress, rss, startup
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            log.close()


@pytest.mark.live
def test_fresh_host_loopback(record_property: pytest.RecordProperty) -> None:
    """AOS-001-TC04. A report cannot supply sockets, startup, or RSS."""
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False)
    record_property("gate_case_id", "AOS-001-TC04")
    record_property("candidate_commit", commit.stdout.strip())
    record_property("lane", "live")
    record_property("execution_mode", "LIVE")
    record_property("aos_001_tc04", "NOT_RUN")
    os_release = Path("/etc/os-release").read_text(encoding="utf-8")
    identity = dict(part.split("=", 1) for part in os_release.splitlines() if "=" in part)
    if identity.get("ID", "").strip('"') != "ubuntu":
        pytest.fail("fresh_host_not_ubuntu")
    for key in _PROVIDER_KEYS:
        if os.environ.get(key, "") != "":
            pytest.fail("provider_credential_present")
    report_path = os.environ.get("PANESTRIA_FRESH_HOST_REPORT", "")
    report: object = None
    if report_path != "":
        report_file = Path(report_path)
        if report_file.is_file():
            report = json.loads(report_file.read_text(encoding="utf-8"))
    boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="utf-8").strip()
    if not fresh_host_attested(report, boot_id):
        pytest.fail("fresh_host_not_attested")
    listens, egress, rss, startup = _measure_loopback_smoke()
    denial = smoke_denial(listens, egress, rss, startup)
    if denial is not None:
        pytest.fail(denial)
    record_property("rss_kb", rss)
    record_property("startup_seconds", f"{startup:.3f}")
    record_property("loopback_listen_count", str(len(listens)))
    record_property("aos_001_tc04", "OBSERVED")
