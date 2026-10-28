"""Actual PG/context/crypto/HTTP, declared runtime/model metadata fixtures unless live."""

import json
import os
import subprocess
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from test_ask_kernel import initialize
from test_local_provider import transport, valid_frames
from test_local_server import ModelFixture
from test_local_server import configured as configured  # noqa: F401
from test_profile_ask import ask_profile as ask_profile  # noqa: F401
from test_profile_style import styled as styled  # noqa: F401
from test_profile_vault import profile as profile  # noqa: F401

from model_manifest_support import model_manifest
from panestria.api import local_server
from panestria.api.main import mount_ask_api, mount_profile_api
from panestria.api.routes.ask import AskApi
from panestria.api.routes.profiles import ProfileApi
from panestria.cli.local_init import first_run_files
from panestria.config import Settings
from panestria.config_local import LocalApplicationRejected, load_local_settings
from panestria.contracts.ask import AskSubmission
from panestria.contracts.inference import InferenceResult, Usage
from panestria.contracts.memory import MemorySubmission
from panestria.inference.local import LocalProvider
from panestria.kernel.ask import AskService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.local_setup import LocalSetupIntent, LocalSetupService
from panestria.kernel.uow import UnitOfWork
from panestria.memory.service import MemoryService
from panestria.resources.hardware import HardwareProbe


@pytest.fixture
def r1_task(r1_migration_task):
    return r1_migration_task


def test_retained_context_identity_replacement_refusal_and_rollback_preserve_data(r1_task, tmp_path, record_property):
    actor, legacy = initialize(r1_task, tmp_path)
    selected = model_manifest()
    original = AskService(model_manifest=selected, include_charter=True)
    replacement = AskService(model_manifest=model_manifest(template_sha256="9" * 64), include_charter=True)
    question = AskSubmission(
        request_id=str(uuid4()), project_id=actor.project_id, question="Recall retained storage", context_tokens=4096
    )
    record_property("mode", "ACTUAL_PG_CONTEXT__EXPLICIT_MODEL_RUNTIME_METADATA_FIXTURES__NO_INFERENCE")
    with psycopg.connect(r1_task["dsn"]) as c:
        uow = UnitOfWork(c)
        fact = MemoryService().add(uow, actor, MemorySubmission(body="Retained storage is PostgreSQL", label="PUBLIC"))
        old = legacy.prepare(uow, actor, question)
        bound = original.prepare(uow, actor, question.model_copy(update={"request_id": str(uuid4())}))
        c.commit()
        original_metadata = c.execute(
            "SELECT metadata FROM panestria.context_pack WHERE id=%s", (bound.context.id,)
        ).fetchone()[0]
        assert original_metadata["model_manifest"] == selected.model_dump(mode="json")
        for tampered in (
            replace(bound, model_manifest=None),
            replace(bound, inference=bound.inference.model_copy(update={"model_manifest_sha256": None})),
        ):
            with pytest.raises(KernelDenied, match="model_manifest_mismatch"), c.transaction():
                original.claim(uow, actor, tampered)
        with pytest.raises(KernelDenied, match="model_manifest_incompatible"), c.transaction():
            replacement.claim(uow, actor, bound)
        # Refusal doesn't mutate/re-render old context, delete memory or renew a deadline.
        assert original.receipt(uow, actor, bound.submission.request_id)["state"] == "PREPARED"
        inferred = original.claim(uow, actor, bound)
        c.commit()
        assert inferred.model_manifest_sha256 == selected.sha256() and inferred.prompt == bound.inference.prompt
        bad = InferenceResult(selected.model_ref, "wrong identity", Usage(2, 2, 0), 0.2, 0.1)
        with pytest.raises(KernelDenied, match="model_manifest_mismatch"), c.transaction():
            original.finish(uow, actor, bound.submission.request_id, bad)
        # A changed new-work default cannot repin an already returned old result.
        replacement.finish(
            uow, actor, bound.submission.request_id, replace(bad, model_manifest_sha256=selected.sha256())
        )
        c.commit()
        receipt = original.receipt(uow, actor, bound.submission.request_id)
        assert receipt["usage"]["model_manifest_sha256"] == selected.sha256()
        assert receipt["model_manifest"] == selected.model_dump(mode="json")
        actual_metadata = c.execute(
            "SELECT metadata FROM panestria.context_pack WHERE id=%s", (bound.context.id,)
        ).fetchone()[0]
        assert actual_metadata == original_metadata
        with pytest.raises(psycopg.Error, match="immutable"), c.transaction():
            c.execute("UPDATE panestria.context_pack SET metadata='{}' WHERE id=%s", (bound.context.id,))
        # Legacy prepared bytes and application-owned memory still work after rollback.
        assert legacy.claim(uow, actor, old).prompt == old.inference.prompt
        c.commit()
        fresh = original.prepare(uow, actor, question.model_copy(update={"request_id": str(uuid4())}))
        assert fact.source_id in {ref.source_id for ref in fresh.context.sources}
        assert fresh.model_manifest == selected


def test_private_setting_reaches_startup_provider_and_canonical_http_receipt(
    configured, tmp_path, tmp_path_factory, monkeypatch, record_property
):
    _config, token, settings, prior, _ = configured
    prior.state.health.shutdown()
    path = tmp_path / "local.json"
    body = json.loads(path.read_text())
    path.write_text(json.dumps({**body, "pin_model_manifest": "true"}))
    with pytest.raises(LocalApplicationRejected):
        load_local_settings(path)
    selected = model_manifest()
    monkeypatch.setattr(ModelFixture, "describe_manifest", lambda self: selected, raising=False)
    path.write_text(
        json.dumps(
            {
                **body,
                "pin_model_manifest": True,
                "runtime_directory": str(tmp_path_factory.mktemp("pin") / "r"),
            }
        )
    )
    config, _ = load_local_settings(path)
    app = local_server.build_local_app(config, settings, token)
    mock, calls = transport(valid_frames())
    app.state.ask_api.provider.transport = mock
    record_property("mode", "ACTUAL_CONFIG_PG_HTTP__EXPLICIT_RUNTIME_MODEL_METADATA_CAPACITY_FIXTURES")
    with TestClient(app, base_url=config.origin) as client:
        headers = {"Authorization": "Bearer " + token}
        status = client.get("/v1/local/status", headers=headers).json()
        assert status["model_manifest"] == selected.model_dump(mode="json")
        assert status["profiles"] == "DISABLED" and status["release_gate"] == "NOT_EVALUATED"
        payload = {"request_id": str(uuid4()), "project_id": str(config.project_id), "question": "Say READY"}
        response = client.post("/v1/ask", json=payload, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["usage"]["model_manifest_sha256"] == selected.sha256()
        assert client.post("/v1/ask", json=payload, headers=headers).json()["replayed_receipt"]
        receipt = client.get("/v1/ask/" + payload["request_id"], headers=headers).json()
        assert receipt["model_manifest"] == selected.model_dump(mode="json") and "text" not in receipt
        assert sum(r.method == "POST" for r in calls) == 1


def test_restricted_profile_stays_encrypted_while_public_manifest_is_pinned(styled, r1_task):
    from test_aos_009 import _client

    dsn, _actor, _handle, _keys, vault, _service, request, preferences = styled
    client = _client(r1_task)
    selected = model_manifest()
    mock, calls = transport(valid_frames())
    provider = LocalProvider(Path("/synthetic"), transport=mock)
    provider.bind_manifest(selected)
    root = Path(__file__).resolve().parents[2]
    mount_ask_api(
        client.app,
        AskApi(
            provider,
            lambda: HardwareProbe(root / "docs/specification/attachments/agentos-skills-v0.1.0.zip").collect(
                preset="omen-8gb"
            ),
            pin_model_manifest=True,
            include_charter=True,
            lossless_presentation=True,
        ),
    )
    mount_profile_api(client.app, ProfileApi(vault))
    headers = {"Authorization": "Bearer test-only-cli-token-at-least-16"}
    response = client.post("/v2/ask", json=request.model_dump(mode="json"), headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["response_sha256"] is None
    assert response.json()["usage"]["model_manifest_sha256"] == selected.sha256()
    assert response.json()["model_manifest"] == selected.model_dump(mode="json")
    assert sum(r.method == "POST" for r in calls) == 1
    with psycopg.connect(dsn) as c:
        for table in ("context_pack", "ask_request", "ask_profile_context", "learning_record"):
            rows = c.execute(f"SELECT row_to_json(t)::text FROM panestria.{table} t").fetchall()
            assert all(preferences.model_dump_json() not in row[0] for row in rows)


@pytest.mark.live
def test_actual_cached_cpu_manifest_startup_ask_and_receipt(r1_database, tmp_path_factory, record_property):
    cache = os.environ.get("PANESTRIA_PROFILE_TEST_MODEL_CACHE")
    if not cache:
        pytest.skip("explicit existing read-only cache not selected; no actual model evidence")
    root = tmp_path_factory.mktemp("manifest") / "owner-test"
    with first_run_files(root, Path(cache), 18762) as config:
        with psycopg.connect(r1_database) as c:
            LocalSetupService().initialize(
                UnitOfWork(c),
                LocalSetupIntent(
                    owner_id=config.owner_id,
                    project_id=config.project_id,
                    intent="OFFLINE_ASK",
                ),
            )
    path = root / "local.json"
    path.write_text(json.dumps({**json.loads(path.read_text()), "pin_model_manifest": True}))
    config, token = load_local_settings(path)
    app = local_server.build_local_app(
        config, Settings(database_url=r1_database).validate_profile(), token.get_secret_value()
    )
    model = app.state.local_model
    assert not model._docker(["ps", "-a", "-q", "--filter", "label=panestria.purpose=local-model"]).strip(), (
        "existing model service preserved; live check not run"
    )
    with TestClient(app, base_url=config.origin) as client:
        headers = {"Authorization": "Bearer " + token.get_secret_value()}
        descriptor = client.get("/v1/local/status", headers=headers).json()["model_manifest"]
        assert descriptor["evaluation"] == "NOT_EVALUATED" and descriptor["tools"] == []
        assert (
            descriptor["quantization"] == "Q4_K_M"
            and descriptor["tokenizer_container_sha256"] == (descriptor["weights_sha256"])
        )
        payload = {
            "request_id": str(uuid4()),
            "project_id": str(config.project_id),
            "question": "Reply with the word READY.",
            "max_output_tokens": 16,
            "deadline_seconds": 60.0,
        }
        answer = client.post("/v1/ask", json=payload, headers=headers)
        assert answer.status_code == 200 and answer.json()["text"], answer.text
        result = answer.json()
        assert result["model_manifest"] == descriptor and result["usage"]["input_tokens"] > 0
        assert result["usage"]["model_manifest_sha256"] == app.state.ask_api.provider.model_manifest.sha256()
        receipt = client.get("/v1/ask/" + payload["request_id"], headers=headers).json()
        assert receipt["model_manifest"] == descriptor and receipt["usage"] == result["usage"]
        assert "text" not in receipt and not receipt["response_retained"]
        assert client.post("/v1/ask", json=payload, headers=headers).json()["replayed_receipt"]
        record_property("model_elapsed_seconds", result["usage"]["elapsed_seconds"])
        record_property("model_input_tokens", result["usage"]["input_tokens"])
        record_property("model_output_tokens", result["usage"]["output_tokens"])
    assert model.id is None
    assert not model._docker(["ps", "-a", "-q", "--filter", "label=panestria.purpose=local-model"]).strip()
    record_property("candidate_commit", subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip())
    record_property("execution_mode", "ACTUAL_CACHED_CPU_DOCKER_UDS_PG_ASGI__NO_PHYSICAL_TCP_OR_QUALITY_QUALIFICATION")
    record_property("model_calls", 1)
    record_property("release_gate", "NOT_EVALUATED")
