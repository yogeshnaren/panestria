"""Restricted Ask bindings use actual ciphertext/PG and no clear-field hashes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from uuid import uuid4

import psycopg
import pytest
from pydantic import SecretStr, ValidationError
from test_ask_kernel import initialize
from test_profile_vault import profile  # noqa: F401

from panestria.contracts.ask import AskSubmission, ProfileAskSubmission
from panestria.contracts.inference import InferenceResult, Usage
from panestria.contracts.profile import ProfileDocument
from panestria.contracts.profile_context import ProfileSelectionRequest
from panestria.kernel.ask import AskService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.uow import UnitOfWork
from panestria.memory.profile import ProfileContext

SENTINEL = "SYNTHETIC_PRIVATE_PROFILE_ASK_世界"


@pytest.fixture
def ask_profile(profile, r1_task, tmp_path):  # noqa: F811
    dsn, actor, handle, keys, vault = profile
    initialize(r1_task, tmp_path)
    with psycopg.connect(dsn) as c:
        vault.create(
            UnitOfWork(c),
            actor,
            handle,
            ProfileDocument(
                fields={"communication": SecretStr(SENTINEL)}, approved_for_local_context=("communication",)
            ),
            consent_ref=str(uuid4()),
        )
    request = ProfileAskSubmission(
        schema_version=2,
        request_id=str(uuid4()),
        project_id=actor.project_id,
        question="Explain my approved communication preference",
        context_tokens=4096,
        profile=ProfileSelectionRequest(
            profile_id=handle.profile_id,
            expected_row_version=0,
            fields=("communication",),
            purpose="RESPONSE_STYLE",
            destination="OFFLINE_LOCAL_MODEL",
        ),
    )
    return dsn, actor, handle, keys, vault, AskService(profile_context=ProfileContext(vault)), request


def prepare(fixture):
    dsn, actor, handle, keys, vault, service, request = fixture
    with psycopg.connect(dsn) as c:
        return service.prepare(UnitOfWork(c), actor, request)


def test_profile_ask_omits_cleartext_and_input_output_fingerprints(ask_profile, caplog):
    dsn, actor, handle, keys, vault, service, request = ask_profile
    prepared = prepare(ask_profile)
    assert SENTINEL in prepared.inference.prompt and SENTINEL not in prepared.context.prompt
    assert prepared.inference.label == "RESTRICTED" and prepared.inference.offline is True
    with psycopg.connect(dsn) as c:
        inference = service.claim(UnitOfWork(c), actor, prepared)
        assert inference.prompt == prepared.inference.prompt
    with psycopg.connect(dsn) as c:
        uow = UnitOfWork(c)
        service.finish(
            uow, actor, request.request_id, InferenceResult(inference.model_ref, SENTINEL, Usage(90, 12, 0), 0.2, 0.1)
        )
        receipt = service.receipt(uow, actor, request.request_id)
        assert receipt["state"] == "COMPLETED" and receipt["response_sha256"] is None
        assert receipt["response_digest_mode"] == "OMITTED_RESTRICTED_PROFILE"
        assert receipt["profile_context"]["profile_id"] == handle.profile_id
        assert receipt["privacy_label"] == "RESTRICTED" and receipt["response_retained"] is False
        forbidden = (
            SENTINEL,
            hashlib.sha256(SENTINEL.encode()).hexdigest(),
            hashlib.sha256(prepared.inference.prompt.encode()).hexdigest(),
        )
        for table in ("context_pack", "ask_request", "ask_profile_context", "profile_revision", "learning_record"):
            rows = c.execute(f"SELECT row_to_json(t)::text FROM panestria.{table} t").fetchall()
            assert all(all(value not in row[0] for value in forbidden) for row in rows)
    assert SENTINEL not in repr(prepared) + caplog.text


@pytest.mark.parametrize(
    "field,value",
    [
        ("offline", False),
        ("offline", 1),
        ("label", "PUBLIC"),
        ("max_output_tokens", 1024),
        ("context_tokens", 512),
        ("model_ref", "unapproved-model"),
    ],
)
def test_forged_inference_denied(ask_profile, field, value):
    dsn, actor, handle, keys, vault, service, request = ask_profile
    prepared = prepare(ask_profile)
    with psycopg.connect(dsn) as c, pytest.raises(KernelDenied, match="context_integrity_failed"):
        service.claim(
            UnitOfWork(c), actor, replace(prepared, inference=prepared.inference.model_copy(update={field: value}))
        )


@pytest.mark.parametrize("fault", ["missing_selection", "content", "source", "binding"])
def test_forged_selection_or_persisted_binding_denied(ask_profile, fault):
    dsn, actor, handle, keys, vault, service, request = ask_profile
    prepared = prepare(ask_profile)
    if fault == "missing_selection":
        prepared = replace(prepared, profile=None)
    elif fault == "content":
        prepared = replace(
            prepared, profile=prepared.profile.model_copy(update={"content": SecretStr("forged preference")})
        )
    elif fault == "source":
        source = replace(prepared.profile.source, revision_id=str(uuid4()))
        prepared = replace(prepared, profile=prepared.profile.model_copy(update={"source": source}))
    with psycopg.connect(dsn) as c:
        if fault == "binding":
            c.execute("ALTER TABLE panestria.ask_profile_context DISABLE TRIGGER immutable_profile_context")
            c.execute(
                "UPDATE panestria.ask_profile_context SET manifest_sha256=%s WHERE request_id=%s",
                ("0" * 64, request.request_id),
            )
        with pytest.raises(KernelDenied, match="profile_context_(integrity_failed|stale)"):
            service.claim(UnitOfWork(c), actor, prepared)
        c.rollback()


@pytest.mark.parametrize("change", ["correction", "suppression", "rotation"])
def test_lifecycle_change_denies_pending_claim(ask_profile, change):
    dsn, actor, handle, keys, vault, service, request = ask_profile
    prepared = prepare(ask_profile)
    with psycopg.connect(dsn) as c:
        if change == "suppression":
            vault.suppress(UnitOfWork(c), actor, handle.profile_id, 0)
        else:
            if change == "rotation":
                handle = handle.model_copy(update={"key_id": str(uuid4())})
                keys.provision(handle)
            vault.revise(
                UnitOfWork(c),
                actor,
                handle,
                0,
                ProfileDocument(
                    fields={"communication": SecretStr("NEW_STATEMENT")}, approved_for_local_context=("communication",)
                ),
                consent_ref=str(uuid4()),
            )
    with psycopg.connect(dsn) as c, pytest.raises(KernelDenied, match="version_conflict|profile_suppressed"):
        service.claim(UnitOfWork(c), actor, prepared)


def test_profile_budget_and_default_service_deny_without_partial_admission(ask_profile):
    dsn, actor, handle, keys, vault, service, request = ask_profile
    with psycopg.connect(dsn) as c:
        with pytest.raises(KernelDenied, match="profile_disabled"), c.transaction():
            AskService().prepare(UnitOfWork(c), actor, request)
        with pytest.raises(KernelDenied, match="profile_context_budget_exceeded"), c.transaction():
            service.prepare(UnitOfWork(c), actor, request.model_copy(update={"context_tokens": 512}))
        assert c.execute(
            "SELECT count(*) FROM panestria.ask_request WHERE id=%s", (request.request_id,)
        ).fetchone() == (0,)


def test_ordinary_ask_cannot_disable_digest_or_gain_late_profile_binding(ask_profile):
    dsn, actor, handle, keys, vault, service, request = ask_profile
    prepare(ask_profile)
    ordinary = AskSubmission(
        request_id=str(uuid4()), project_id=actor.project_id, question="Ordinary synthetic request"
    )
    with pytest.raises(ValidationError):
        AskSubmission.model_validate({**ordinary.model_dump(), "response_digest_mode": "OMITTED_RESTRICTED_PROFILE"})
    with psycopg.connect(dsn) as c:
        AskService().prepare(UnitOfWork(c), actor, ordinary)
    with psycopg.connect(dsn) as c:
        with pytest.raises(psycopg.Error, match="identity is immutable"), c.transaction():
            c.execute(
                "UPDATE panestria.ask_request SET response_digest_mode='OMITTED_RESTRICTED_PROFILE' WHERE id=%s",
                (ordinary.request_id,),
            )
        with pytest.raises(psycopg.Error, match="profile_ask_digest_mode_invalid"), c.transaction():
            c.execute(
                "INSERT INTO panestria.ask_profile_context SELECT %s,owner_id,project_id,source_revision_id,profile_id,"
                "profile_version,row_version,key_id,ciphertext_sha256,request_body,selection_sha256,manifest_sha256,"
                "policy_ref,render_version,privacy_label,created_at FROM panestria.ask_profile_context"
                " WHERE request_id=%s",
                (ordinary.request_id, request.request_id),
            )
            c.execute("SET CONSTRAINTS ALL IMMEDIATE")


@pytest.mark.parametrize(
    "mutation",
    [
        {"schema_version": True},
        {"schema_version": 2.0},
        {"privacy_label": "PUBLIC"},
        {"offline": False},
        {"offline": 1},
        {"retain_response": 0},
    ],
)
def test_profile_ask_contract_rejects_downgrade_or_invalid_version(ask_profile, mutation):
    request = ask_profile[-1]
    with pytest.raises(ValidationError):
        ProfileAskSubmission.model_validate_json(json.dumps({**request.model_dump(mode="json"), **mutation}))
