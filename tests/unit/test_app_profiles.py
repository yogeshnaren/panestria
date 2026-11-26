"""Golden surface of every product server mode.

Each mode is built through the same public builder its server uses, without a
database, model or network. The snapshot records, per mode:

- routes in registration order (hidden ones marked), middleware order and the
  ``app.state`` slots the mounts set;
- the browser session scope: cookie namespace, cookie name, lifetime and a
  fingerprint of the derived session key, so two modes that share a key show
  the same fingerprint;
- what a fixed set of probe requests receives (status, error code, headers),
  plus the bearer-authenticated Mission Control capabilities;
- the operations and component schemas the mode would publish in OpenAPI.

A deliberate surface change regenerates the file and shows up in review:

    UPDATE_GOLDEN=1 uv run pytest tests/unit/test_app_profiles.py
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from panestria.api.activity_server import build_activity_app
from panestria.api.app import build_app
from panestria.api.auth import GoalApi
from panestria.api.local_server import build_local_app
from panestria.api.mission_web import mount_mission_control
from panestria.api.routes.profiles import ProfileApi
from panestria.api.security import _SECURITY_HEADERS
from panestria.api.serve import goal_profile
from panestria.api.sessions import BrowserAccess
from panestria.config import Settings
from panestria.config_activity import ActivitySettings
from panestria.config_local import LocalApplicationSettings
from panestria.config_phone import PhoneSettings
from panestria.memory.vault import ProfileVault

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests/fixtures/golden/app-profiles-v1.json"

OWNER = "00000000-0000-4000-8000-0000000000a1"
PROJECT = "00000000-0000-4000-8000-0000000000a2"
TOKEN = "synthetic-loopback-token"
DSN = "postgresql://panestria_synthetic:placeholder-not-a-secret@127.0.0.1:1/panestria_synthetic"
GOAL = "00000000-0000-4000-8000-0000000000a3"
# Fixed, never-read paths: they feed scope digests, so they must not vary per run.
FIXED = Path("/nonexistent/panestria-golden")
FOREIGN_ORIGIN = "http://foreign.invalid"
_VOLATILE_HEADERS = {"date", "content-length"}


@dataclass(frozen=True)
class Env:
    activity: ActivitySettings
    local: LocalApplicationSettings
    phone: PhoneSettings
    assets: Path
    review_root: Path
    evidence: Path


class _StubRun:
    """Stands in for MissionRunService, which loads an owner's Build configuration."""

    def __init__(self, path: Path, actor: object, dsn: str) -> None:
        del path, actor, dsn
        self.settings = SimpleNamespace(root=_StubRun.root)
        self.configuration = hashlib.sha256(b"golden-build-run").hexdigest()

    root: Path = FIXED

    def close(self) -> None:
        pass


class _StubResearch:
    """Stands in for ResearchIntakeService, which reads a private intake template."""

    def __init__(self, path: Path, actor: object) -> None:
        del path, actor
        self.view = SimpleNamespace(template_sha256=hashlib.sha256(b"golden-research").hexdigest())


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Env]:
    root = tmp_path.resolve()
    assets = root / "assets"
    assets.mkdir(mode=0o700)
    (assets / "index.html").write_bytes(b'<!doctype html><div id="root"></div>')
    (assets / "mission.js").write_bytes(b"/* golden */")
    (assets / "mission.css").write_bytes(b"/* golden */")
    review_root = root / "review"
    (review_root / "reports").mkdir(parents=True, mode=0o700)
    review_root.chmod(0o700)
    evidence = root / "evidence"
    evidence.mkdir(mode=0o700)
    _StubRun.root = review_root
    monkeypatch.setattr("panestria.execution.mission_run.MissionRunService", _StubRun)
    monkeypatch.setattr("panestria.execution.research_intake.ResearchIntakeService", _StubResearch)
    # The phone scope digests the certificate bytes; the file itself is never served here.
    monkeypatch.setattr("panestria.api.phone.read_private", lambda path, limit: b"golden-certificate")
    common: dict[str, Any] = {"schema_version": 1, "owner_id": UUID(OWNER), "project_id": UUID(PROJECT)}
    yield Env(
        activity=ActivitySettings(**common, bind_port=8769, token_file=FIXED / "activity.token"),
        local=LocalApplicationSettings(
            **common,
            bind_port=8766,
            token_file=FIXED / "local.token",
            model_cache=FIXED / "models",
            runtime_directory=FIXED / "run",
        ),
        phone=PhoneSettings(
            **common,
            bind_port=8443,
            token_file=FIXED / "activity.token",
            enabled=True,
            bind_address="10.0.0.1",
            allowed_clients=("10.0.0.2",),
            certificate_file=FIXED / "phone.crt",
            key_file=FIXED / "phone.key",
        ),
        assets=assets,
        review_root=review_root,
        evidence=evidence,
    )


def _settings() -> Any:
    return Settings(database_url=DSN).validate_profile()


def _goal_api(env: Env) -> FastAPI:
    # As ``python -m panestria.api.serve`` assembles it.
    return build_app(goal_profile(_settings(), GoalApi(TOKEN, OWNER, PROJECT, DSN), FIXED / "sandbox"))


def _mission(**modes: Any) -> Callable[[Env], FastAPI]:
    """As ``panestria mission serve`` assembles it; a callable mode value takes the env."""

    def build(env: Env) -> FastAPI:
        storage = FIXED / "storage.json" if modes.get("storage_mode") else None
        app = build_activity_app(env.activity, _settings(), TOKEN, storage_config=storage)
        selected = {key: value(env) if callable(value) else value for key, value in modes.items()}
        mount_mission_control(app, env.activity, TOKEN, env.assets, **selected)
        return app

    return build


def _phone(env: Env) -> FastAPI:
    from panestria.api.phone import build_phone_app

    return build_phone_app(env.phone, _settings(), TOKEN, env.assets)


def _profiles_api() -> ProfileApi:
    return ProfileApi(ProfileVault(SimpleNamespace(), enabled=True))


PROFILES: dict[str, Callable[[Env], FastAPI]] = {
    "goal-api": _goal_api,
    "ask-web": lambda env: build_local_app(env.local, _settings(), TOKEN),
    "ask-profiles": lambda env: build_local_app(env.local, _settings(), TOKEN, profiles=_profiles_api()),
    "ask-mission": lambda env: build_local_app(env.local, _settings(), TOKEN, mission_assets=env.assets),
    "activity": lambda env: build_activity_app(env.activity, _settings(), TOKEN),
    "activity-storage": lambda env: build_activity_app(
        env.activity, _settings(), TOKEN, storage_config=FIXED / "storage.json"
    ),
    "connection-reviews": lambda env: build_activity_app(env.activity, _settings(), TOKEN, connection_reviews=True),
    "mission": _mission(),
    "mission-evidence": _mission(build_evidence_store=lambda env: env.evidence),
    "mission-review": _mission(build_review_root=lambda env: env.review_root),
    "mission-research": _mission(research_intake=FIXED / "research.json"),
    "mission-build-intake": _mission(build_intake=True),
    "mission-plan-review": _mission(build_plan_review=True),
    "mission-build-run": _mission(build_run=FIXED / "build.json"),
    "mission-storage": _mission(storage_mode=True),
    "phone": _phone,
}


def _routes(routes: list[Any], prefix: str = "") -> list[str]:
    """Flatten included routers (FastAPI keeps them nested) in matching order."""
    found = []
    for route in routes:
        original = getattr(route, "original_router", None)
        if original is not None:
            context = route.include_context
            found += [
                f"{entry} [router-hidden]" if not context.include_in_schema else entry
                for entry in _routes(original.routes, prefix + context.prefix)
            ]
            continue
        methods = ",".join(sorted(getattr(route, "methods", None) or [])) or "-"
        hidden = "" if getattr(route, "include_in_schema", True) else " [hidden]"
        found.append(f"{methods} {prefix}{getattr(route, 'path', type(route).__name__)}{hidden}")
    return found


def _state(app: FastAPI) -> dict[str, str]:
    described = {}
    for key, value in sorted(app.state._state.items()):
        if isinstance(value, bool) or value is None:
            described[key] = repr(value)
        else:
            described[key] = type(value).__name__
    return described


def _browser(app: FastAPI) -> dict[str, Any] | None:
    access = getattr(app.state, "browser_access", None)
    if not isinstance(access, BrowserAccess):
        return None
    return {
        "namespace": access.namespace,
        "cookie_name": access.cookie_name,
        "session_seconds": access.session_seconds,
        "secure": access.secure,
        "key_fingerprint": hashlib.sha256(access.service._secret).hexdigest()[:16],
    }


def _response(response: Any) -> dict[str, Any]:
    described: dict[str, Any] = {"status": response.status_code}
    if response.headers.get("content-type", "").startswith("application/json"):
        body = response.json()
        if isinstance(body, dict) and "code" in body:
            described["code"] = body["code"]
    headers = {k: v for k, v in sorted(response.headers.items()) if k not in _VOLATILE_HEADERS}
    if all(headers.get(name) == value for name, value in _SECURITY_HEADERS.items()):
        # The full browser envelope, exactly; any other value is recorded as is.
        headers = {k: v for k, v in headers.items() if k not in _SECURITY_HEADERS}
        described["security_headers"] = "standard"
    described["headers"] = headers
    return described


def _probes(app: FastAPI, origin: str) -> dict[str, Any]:
    client_address = ("10.0.0.2", 50000) if origin.startswith("https://") else ("127.0.0.1", 50000)
    client = TestClient(app, base_url=origin, client=client_address)
    bearer = {"authorization": f"Bearer {TOKEN}"}
    probes = {
        "GET /healthz": client.get("/healthz"),
        "GET /": client.get("/"),
        "GET /v1/activity (anonymous)": client.get("/v1/activity"),
        "GET /v1/goals/{id} (anonymous)": client.get(f"/v1/goals/{GOAL}"),
        "GET /v1/local/status (anonymous)": client.get("/v1/local/status"),
        "POST /v1/session/pair (foreign origin)": client.post(
            "/v1/session/pair", json={"code": "0" * 8}, headers={"origin": FOREIGN_ORIGIN}
        ),
    }
    described = {name: _response(response) for name, response in probes.items()}
    capabilities = client.get("/v1/mission/capabilities", headers=bearer)
    described["GET /v1/mission/capabilities (bearer)"] = _response(capabilities)
    if capabilities.status_code == 200:
        described["capabilities"] = capabilities.json()
    return described


def _openapi(app: FastAPI, schemas: dict[str, str]) -> dict[str, Any]:
    """Operations per mode; component schemas by name, with their digests pooled in ``schemas``."""
    document = app.openapi()
    operations = {}
    for path, methods in sorted(document.get("paths", {}).items()):
        for method, operation in sorted(methods.items()):
            responses = ",".join(sorted(operation.get("responses", {})))
            operations[f"{method.upper()} {path}"] = f"{operation.get('operationId')} -> {responses}"
    names = []
    for name, schema in sorted(document.get("components", {}).get("schemas", {}).items()):
        digest = hashlib.sha256(json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]
        assert schemas.setdefault(name, digest) == digest, f"schema {name} differs between modes"
        names.append(name)
    return {"operations": operations, "schemas": names}


def _origin(name: str, env: Env) -> str:
    if name == "phone":
        return env.phone.origin
    if name.startswith("ask-"):
        return env.local.origin
    return env.activity.origin


def snapshot(name: str, env: Env, schemas: dict[str, str]) -> dict[str, Any]:
    app = PROFILES[name](env)
    try:
        return {
            "routes": _routes(app.routes),
            "middleware": [entry.cls.__name__ for entry in app.user_middleware],  # type: ignore[attr-defined]
            "state": _state(app),
            "browser": _browser(app),
            "probes": _probes(app, _origin(name, env)),
            "openapi": _openapi(app, schemas),
        }
    finally:
        app.state.health.shutdown()


def test_every_server_mode_matches_its_golden_surface(env: Env) -> None:
    schemas: dict[str, str] = {}
    current = {name: snapshot(name, env, schemas) for name in PROFILES}
    text = json.dumps({"schema_version": 1, "profiles": current, "schemas": schemas}, indent=2, sort_keys=True)
    text += "\n"
    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN.write_text(text, encoding="utf-8")
        pytest.skip("golden regenerated; review the diff")
    stored = json.loads(GOLDEN.read_text(encoding="utf-8"))
    golden = stored["profiles"]
    assert sorted(golden) == sorted(current), "a server mode was added or removed"
    for name in PROFILES:
        assert current[name] == golden[name], f"{name}: surface changed; regenerate only if intended"
    assert schemas == stored["schemas"], "an OpenAPI component schema changed"


def test_modes_with_different_session_namespaces_never_share_a_session_key() -> None:
    # A session minted under one key authenticates wherever that key is used,
    # whatever the cookie is called. Distinct authority needs distinct keys.
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))["profiles"]
    namespaces_by_key: dict[str, set[str]] = {}
    for profile in golden.values():
        if profile["browser"] is not None:
            browser = profile["browser"]
            namespaces_by_key.setdefault(browser["key_fingerprint"], set()).add(browser["namespace"])
    assert len(namespaces_by_key) > 1
    assert all(len(namespaces) == 1 for namespaces in namespaces_by_key.values()), namespaces_by_key
