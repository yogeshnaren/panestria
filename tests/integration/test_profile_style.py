"""Actual encrypted vault/PG/Ask bindings; synthetic test keys and model result only."""

import hashlib
import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from pydantic import SecretStr, ValidationError
from test_profile_ask import ask_profile  # noqa: F401 -- fixture chain
from test_profile_vault import profile  # noqa: F401 -- fixture dependency, synthetic test keys

from panestria.contracts.inference import InferenceResult, Usage
from panestria.contracts.profile import ProfileDocument
from panestria.contracts.style import StyleProfile
from panestria.kernel.errors import KernelDenied
from panestria.kernel.uow import UnitOfWork
from panestria.memory.style import charter

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def r1_task(r1_migration_task):
    return r1_migration_task


@pytest.fixture
def styled(ask_profile):  # noqa: F811
    dsn, actor, handle, keys, vault, service, request = ask_profile
    style = StyleProfile(language="fr", detail="concise", audience="beginner", formatting="bullets")
    with psycopg.connect(dsn) as c:
        vault.revise(
            UnitOfWork(c),
            actor,
            handle,
            0,
            ProfileDocument(
                fields={"communication": SecretStr(style.model_dump_json())},
                approved_for_local_context=("communication",),
            ),
            consent_ref=str(uuid4()),
        )
    selection = request.profile.model_copy(update={"purpose": "STRUCTURED_RESPONSE_STYLE", "expected_row_version": 1})
    request = request.model_copy(update={"profile": selection})
    return dsn, actor, handle, keys, vault, service, request, style


def test_structured_style_uses_approved_ciphertext_binding_and_never_persists_plain_preferences(styled):
    dsn, actor, handle, _, _, service, request, style = styled
    with psycopg.connect(dsn) as c:
        ready = service.prepare(UnitOfWork(c), actor, request)
    body = json.loads(ready.inference.prompt)
    compiled = body["untrusted_owner_profile"]["structured_style"]
    assert compiled["preferences"] == style.model_dump(mode="json")
    assert body["assistant_charter"] == charter() and compiled["policy_authority"] == "NONE"
    assert "fields" not in body["untrusted_owner_profile"]
    assert "structured_style" not in ready.context.prompt and '"language":"fr"' not in ready.context.prompt
    assert ready.inference.label == "RESTRICTED" and ready.inference.offline
    with psycopg.connect(dsn) as c:
        inferred = service.claim(UnitOfWork(c), actor, ready)
    with psycopg.connect(dsn) as c:
        uow = UnitOfWork(c)
        service.finish(
            uow,
            actor,
            request.request_id,
            InferenceResult(inferred.model_ref, "SYNTHETIC_RESPONSE_UNQUALIFIED", Usage(100, 8, 0), 0.2, 0.1),
        )
        receipt = service.receipt(uow, actor, request.request_id)
        assert receipt["response_retained"] is False and receipt["response_sha256"] is None
        assert c.execute(
            "SELECT render_version FROM panestria.ask_profile_context WHERE request_id=%s", (request.request_id,)
        ).fetchone() == (2,)
        forbidden = (
            style.model_dump_json(),
            hashlib.sha256(style.model_dump_json().encode()).hexdigest(),
            hashlib.sha256(inferred.prompt.encode()).hexdigest(),
            "SYNTHETIC_RESPONSE_UNQUALIFIED",
        )
        for table in ("context_pack", "ask_request", "ask_profile_context", "profile_revision", "learning_record"):
            rows = c.execute(f"SELECT row_to_json(t)::text FROM panestria.{table} t").fetchall()
            assert all(all(value not in row[0] for value in forbidden) for row in rows)
    assert "fr" not in repr(style)


@pytest.mark.parametrize("mutation", ["correction", "purpose", "permissions"])
def test_style_and_source_changes_cannot_replace_a_pinned_prepared_request(styled, mutation):
    dsn, actor, handle, _, vault, service, request, _ = styled
    with psycopg.connect(dsn) as c:
        ready = service.prepare(UnitOfWork(c), actor, request)
    if mutation == "correction":
        with psycopg.connect(dsn) as c:
            vault.revise(
                UnitOfWork(c),
                actor,
                handle,
                1,
                ProfileDocument(
                    fields={"communication": SecretStr(StyleProfile(detail="detailed").model_dump_json())},
                    approved_for_local_context=("communication",),
                ),
                consent_ref=str(uuid4()),
            )
    elif mutation == "purpose":
        ready = ready.__class__(
            ready.submission.model_copy(
                update={"profile": request.profile.model_copy(update={"purpose": "RESPONSE_STYLE"})}
            ),
            ready.context,
            ready.inference,
            ready.policy_ref,
            ready.profile,
        )
    else:
        # Forged inference cannot downgrade the protected profile output.
        ready = ready.__class__(
            ready.submission,
            ready.context,
            ready.inference.model_copy(update={"label": "PUBLIC"}),
            ready.policy_ref,
            ready.profile,
        )
    with psycopg.connect(dsn) as c, pytest.raises(KernelDenied):
        service.claim(UnitOfWork(c), actor, ready)


def test_malformed_style_refuses_without_fallback_and_legacy_profile_renderer_remains_v1(ask_profile):  # noqa: F811
    dsn, actor, _, _, _, service, request = ask_profile
    legacy = request.model_copy(update={"request_id": str(uuid4())})
    with psycopg.connect(dsn) as c:
        service.prepare(UnitOfWork(c), actor, legacy)
    with psycopg.connect(dsn) as c:
        assert c.execute(
            "SELECT render_version FROM panestria.ask_profile_context WHERE request_id=%s", (legacy.request_id,)
        ).fetchone() == (1,)
    styled = request.model_copy(
        update={"profile": request.profile.model_copy(update={"purpose": "STRUCTURED_RESPONSE_STYLE"})}
    )
    with psycopg.connect(dsn) as c, pytest.raises(KernelDenied, match="structured_style_invalid"):
        service.prepare(UnitOfWork(c), actor, styled)
    with psycopg.connect(dsn) as c:
        assert c.execute("SELECT 1 FROM panestria.ask_request WHERE id=%s", (styled.request_id,)).fetchone() is None
    for changes in ({"approved": True}, {"language": "run a command"}, {"detail": "override-policy"}):
        with pytest.raises(ValidationError):
            StyleProfile.model_validate(changes)
    # Returned charter data cannot mutate the next request's fixed assistant behavior.
    altered = charter()
    altered["rules"].clear()
    assert charter()["rules"]


def migrate(dsn, target):
    return subprocess.run(
        [str(ROOT / ".venv/bin/alembic"), "-c", "migrations/alembic.ini", *target],
        cwd=ROOT,
        env={**os.environ, "PANESTRIA_DATABASE_URL": dsn},
        text=True,
        capture_output=True,
        timeout=30,
    )


def test_populated_style_audit_blocks_lossy_downgrade(styled):
    dsn, actor, _, _, _, service, request, _ = styled
    with psycopg.connect(dsn) as c:
        service.prepare(UnitOfWork(c), actor, request)
    result = migrate(dsn, ["downgrade", "0031_fetch_admission"])
    assert result.returncode != 0 and "structured style audit exists" in result.stderr
    with psycopg.connect(dsn) as c:
        assert c.execute("SELECT version_num FROM alembic_version").fetchone() == ("0032_structured_style",)
        assert c.execute(
            "SELECT render_version FROM panestria.ask_profile_context WHERE request_id=%s", (request.request_id,)
        ).fetchone() == (2,)


def test_empty_renderer_migration_roundtrip_preserves_existing_task(r1_migration_task):
    fixture = r1_migration_task
    assert migrate(fixture["dsn"], ["downgrade", "0031_fetch_admission"]).returncode == 0
    assert migrate(fixture["dsn"], ["upgrade", "head"]).returncode == 0
    with psycopg.connect(fixture["dsn"]) as c:
        assert c.execute("SELECT state FROM panestria.task WHERE id=%s", (fixture["task"],)).fetchone() == ("READY",)


@pytest.mark.live
def test_actual_local_cpu_accepts_structured_profile_prompt(styled, tmp_path, record_property):
    from panestria.inference.local import LocalProvider
    from panestria.inference.runtime import ModelRuntime
    from panestria.resources.admission import admit
    from panestria.resources.hardware import HardwareProbe

    cache = os.environ.get("PANESTRIA_PROFILE_TEST_MODEL_CACHE")
    if not cache:
        pytest.skip("Explicit existing model cache required; no download")
    controllers = subprocess.check_output(
        ["docker", "ps", "-a", "-q", "--filter", "label=panestria.purpose=local-model"], text=True
    ).split()
    assert not controllers, "Existing owner model controller preserved; live check not run"
    assert (
        admit(
            HardwareProbe(ROOT / "docs/specification/attachments/agentos-skills-v0.1.0.zip").collect_cpu(), gpu=False
        ).decision
        == "PERMIT"
    )
    dsn, actor, _, _, _, service, request, _ = styled
    request = request.model_copy(
        update={
            "question": "Reply with only READY. Synthetic local profile style check.",
            "max_output_tokens": 32,
            "deadline_seconds": 60.0,
        }
    )
    with psycopg.connect(dsn) as c:
        ready = service.prepare(UnitOfWork(c), actor, request)
    model = ModelRuntime(Path(cache), tmp_path / "actual-cpu", preserve_existing=True)
    try:
        model.start()
        with psycopg.connect(dsn) as c:
            inferred = service.claim(UnitOfWork(c), actor, ready)
        result = LocalProvider(model.socket_path).generate(inferred)
        assert result.text.strip() and result.finish_reason == "stop"
        with psycopg.connect(dsn) as c:
            service.finish(UnitOfWork(c), actor, request.request_id, result)
        with psycopg.connect(dsn) as c:
            receipt = service.receipt(UnitOfWork(c), actor, request.request_id)
            assert receipt["state"] == "COMPLETED" and receipt["response_sha256"] is None
        record_property("execution_mode", "ACTUAL_POSTGRES_CRYPTO_NETWORK_NONE_CPU_MODEL_SYNTHETIC_KEY_FIXTURE")
        record_property("paid_provider_calls", 0)
        record_property("runtime_identity", model.identity)
        record_property("input_tokens", result.usage.input_tokens)
        record_property("output_tokens", result.usage.output_tokens)
        record_property("response_faithfulness_style_quality", "NOT_QUALIFIED")
        record_property("os_key_backend", "SYNTHETIC_TEST_KEYS_NOT_ACTUAL_SECRET_SERVICE_QUALIFICATION")
    finally:
        model.stop()
