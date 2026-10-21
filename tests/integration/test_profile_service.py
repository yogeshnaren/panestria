"""Actual PG/crypto/HTTP; qualification/key/model identities are explicit fixtures."""

import hashlib
import json
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretBytes
from test_local_server import configuration
from test_local_server import configured as configured
from typer.testing import CliRunner

from panestria.api import local_server, profile_server
from panestria.api.routes.profiles import ProfileApi
from panestria.cli.main import app as cli
from panestria.config_local import LocalApplicationRejected
from panestria.config_profile_service import load_profile_service
from panestria.kernel.build import BuildEvidenceStore
from panestria.memory import profile_runtime
from panestria.memory.keys import KeyStoreUnavailable, ProfileKeyHandle
from panestria.memory.profile_runtime import MODES, NODES, ProfileQualification, QualifiedProfileKeys, validate_junit
from panestria.memory.vault import ProfileVault


class FixtureKeys:
    calls = 0

    def load(self, handle):
        self.calls += 1
        return SecretBytes(b"s" * 32)


def proof(root, inputs, *, expires=False, fault=None):
    candidate = "f" * 40
    xml = ET.Element("testsuites")
    for node, mode in zip(NODES, MODES, strict=True):
        module, name = node.split("::")
        case = ET.SubElement(xml, "testcase", classname=module.replace("/", ".")[:-3], name=name)
        props = ET.SubElement(case, "properties")
        for key, value in {"candidate_commit": candidate, "worktree_state": "clean", "execution_mode": mode}.items():
            ET.SubElement(props, "property", name=key, value=value)
        if fault:
            ET.SubElement(case, fault)
    raw = ET.tostring(xml)
    store = BuildEvidenceStore(root)
    now = datetime.now(UTC)
    offset = timedelta(hours=2) if expires else timedelta(0)
    body = ProfileQualification(
        candidate_commit=candidate,
        runtime_inputs=inputs,
        observed_at=now - offset,
        expires_at=now - offset + timedelta(hours=1),
        cases=NODES,
        raw_junit_sha256=store.write_report(raw),
    )
    return store.write_report(body.model_dump_json().encode()), raw


def test_service_private_config_scope_and_explicit_cli_intent(tmp_path, monkeypatch, record_property):
    path, body = configuration(tmp_path)
    handle = ProfileKeyHandle(
        owner_id=body["owner_id"], project_id=body["project_id"], profile_id=str(uuid4()), key_id=str(uuid4())
    )
    config = tmp_path / "personal.json"
    data = {
        "schema_version": 1,
        "local_config": str(path),
        "qualification_directory": str(tmp_path / "proofs"),
        "qualification_sha256": "a" * 64,
        "key_handles": [handle.model_dump()],
    }
    config.write_text(json.dumps(data))
    config.chmod(0o600)
    parsed, local, _ = load_profile_service(config)
    assert str(local.owner_id) == handle.owner_id and parsed.key_handles == (handle,)
    for change in (
        {"enable_profiles": True},
        {"schema_version": True},
        {"key_handles": [handle.model_dump()] * 2},
        {"key_handles": [{**handle.model_dump(), "project_id": str(uuid4())}]},
        {"qualification_directory": str(local.model_cache / "proofs")},
    ):
        config.write_text(json.dumps({**data, **change}))
        with pytest.raises(LocalApplicationRejected, match="invalid_profile_service_configuration"):
            load_profile_service(config)
    config.write_text(json.dumps(data))
    missing = CliRunner().invoke(cli, ["profile", "serve", "--config", str(config)])
    assert missing.exit_code == 2 and "explicit_restricted_offline_intent_required" in missing.output
    # The supported CLI must not start anything from a missing/unqualified proof.
    started = []
    monkeypatch.setattr(profile_server, "serve_local", lambda *a, **k: started.append(k))
    denied = CliRunner().invoke(cli, ["profile", "serve", "--config", str(config), "--restricted-offline"])
    assert denied.exit_code == 2 and not started
    inputs = {"explicit": "TEST_FIXTURE_NOT_LIVE"}
    monkeypatch.setattr(profile_runtime, "runtime_inputs", lambda: inputs.copy())
    digest, _ = proof(tmp_path / "proofs", inputs)
    config.write_text(json.dumps({**data, "qualification_sha256": digest}))
    underlying = FixtureKeys()
    monkeypatch.setattr(profile_server, "SecretServiceProfileKeys", lambda: underlying)
    accepted = CliRunner().invoke(cli, ["profile", "serve", "--config", str(config), "--restricted-offline"])
    assert accepted.exit_code == 0 and len(started) == 1 and underlying.calls == 1
    assert started[0]["profiles"].vault.enabled
    record_property("qualification_identity", "TEST_FIXTURE_NOT_LIVE")


@pytest.fixture
def personal(configured, tmp_path, monkeypatch):
    config, token, settings, unused_app, calls = configured
    unused_app.state.health.shutdown()
    inputs = {"explicit": "TEST_FIXTURE_NOT_LIVE"}
    monkeypatch.setattr(profile_runtime, "runtime_inputs", lambda: inputs.copy())
    handle = ProfileKeyHandle(
        owner_id=str(config.owner_id), project_id=str(config.project_id), profile_id=str(uuid4()), key_id=str(uuid4())
    )
    digest, raw = proof(tmp_path / "proofs", inputs)
    underlying = FixtureKeys()
    keys = QualifiedProfileKeys(tmp_path / "proofs", digest, (handle,), underlying)
    app = local_server.build_local_app(config, settings, token, profiles=ProfileApi(ProfileVault(keys, enabled=True)))
    mocked = unused_app.state.ask_api.provider.transport
    app.state.ask_api.provider.transport = mocked
    return config, token, settings, app, keys, handle, inputs, underlying, calls


def create(client, token, handle):
    headers = {"Authorization": "Bearer " + token}
    body = {
        "schema_version": 1,
        "profile_id": handle.profile_id,
        "key_id": handle.key_id,
        "intent": "SAVE_RESTRICTED_PROFILE",
        "document": {"fields": {"communication": "SYNTHETIC_STYLE"}, "approved_for_local_context": ["communication"]},
    }
    created = client.post("/v2/profiles", headers=headers, json=body)
    assert created.status_code == 201
    return headers


def request(handle):
    return {
        "schema_version": 2,
        "request_id": str(uuid4()),
        "project_id": handle.project_id,
        "question": "Reply READY",
        "context_tokens": 4096,
        "max_output_tokens": 32,
        "profile": {
            "profile_id": handle.profile_id,
            "expected_row_version": 0,
            "fields": ["communication"],
            "purpose": "RESPONSE_STYLE",
            "destination": "OFFLINE_LOCAL_MODEL",
        },
    }


def test_qualified_existing_handles_serve_profile_ask_and_preserve_default(personal, record_property):
    config, token, settings, app, keys, handle, inputs, underlying, calls = personal
    with TestClient(app, base_url=config.origin) as client:
        headers = create(client, token, handle)
        assert client.get("/v1/local/status", headers=headers).json()["profiles"] == "EXPLICITLY_ENABLED"
        assert client.post("/v1/goals", json={}, headers=headers).status_code == 404
        response = client.post("/v2/ask", json=request(handle), headers=headers)
        assert response.status_code == 200 and response.json()["state"] == "COMPLETED"
        assert response.json()["text"] == "READY" and response.json()["response_sha256"] is None
        assert sum(r.url.path == "/api/generate" for r in calls) == 1
        used = underlying.calls
        wrong = handle.model_copy(update={"key_id": str(uuid4())})
        with pytest.raises(KeyStoreUnavailable, match="profile_key_not_selected"):
            keys.load(wrong)
        assert underlying.calls == used
        inputs["changed"] = "runtime"
        denied = client.post(
            f"/v2/profiles/{handle.profile_id}/view",
            json={"schema_version": 1, "expected_version": 0, "purpose": "OWNER_REVIEW"},
            headers=headers,
        )
        assert denied.json()["code"] == "profile_qualification_invalid_or_expired"
        assert underlying.calls == used
        suppressed = client.post(
            f"/v2/profiles/{handle.profile_id}/suppress",
            json={"schema_version": 1, "expected_version": 0},
            headers=headers,
        )
        assert suppressed.status_code == 200 and suppressed.json()["state"] == "SUPPRESSED"
    assert app.state.local_model.stopped_fixture
    record_property("qualification_identity", "TEST_FIXTURE_NOT_LIVE")


def test_changed_runtime_after_model_return_fences_clear_answer_publication(personal, record_property):
    config, token, settings, app, keys, handle, inputs, underlying, calls = personal

    import httpx2 as httpx

    original = app.state.ask_api.provider.transport

    async def changed(req):
        response = await original.handle_async_request(req)
        if req.url.path == "/api/generate":
            inputs["changed"] = "during model call"
        return response

    app.state.ask_api.provider.transport = httpx.MockTransport(changed)
    with TestClient(app, base_url=config.origin) as client:
        headers = create(client, token, handle)
        submission = request(handle)
        response = client.post("/v2/ask", headers=headers, json=submission)
        assert response.json()["code"] == "profile_qualification_invalid_or_expired" and "text" not in response.json()
        assert sum(r.url.path == "/api/generate" for r in calls) == 1
        with psycopg.connect(settings.database_url.get_secret_value()) as c:
            assert c.execute(
                "SELECT state,response_sha256 FROM panestria.ask_request WHERE id=%s", (submission["request_id"],)
            ).fetchone() == ("UNAVAILABLE", None)
    record_property("qualification_identity", "TEST_FIXTURE_NOT_LIVE")


def test_expiry_corruption_and_skipped_live_evidence_are_not_qualification(tmp_path, monkeypatch):
    inputs = {"explicit": "TEST_FIXTURE_NOT_LIVE"}
    monkeypatch.setattr(profile_runtime, "runtime_inputs", lambda: inputs)
    digest, raw = proof(tmp_path / "expired", inputs, expires=True)
    keys = QualifiedProfileKeys(tmp_path / "expired", digest, (), FixtureKeys())
    with pytest.raises(KeyStoreUnavailable, match="profile_qualification_invalid_or_expired"):
        keys.validate()
    for fault in ("skipped", "failure", "error"):
        _, bad = proof(tmp_path / fault, inputs, fault=fault)
        with pytest.raises(KeyStoreUnavailable, match="profile_qualification_evidence_incomplete"):
            validate_junit(bad, "f" * 40)
    digest, raw = proof(tmp_path / "corrupt", inputs)
    (tmp_path / "corrupt" / digest).chmod(0o600)
    (tmp_path / "corrupt" / digest).write_bytes(b"{}")
    keys = QualifiedProfileKeys(tmp_path / "corrupt", digest, (), FixtureKeys())
    with pytest.raises(KeyStoreUnavailable, match="profile_qualification_invalid_or_expired"):
        keys.validate()
    assert hashlib.sha256(raw).hexdigest()
