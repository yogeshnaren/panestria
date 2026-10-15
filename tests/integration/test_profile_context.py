"""Actual ciphertext reads plus policy and cacheless selection failure cases."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest
from pydantic import SecretStr, ValidationError
from test_ask_kernel import initialize
from test_profile_vault import profile  # noqa: F401

from panestria.contracts.policy import AutonomyAxis
from panestria.contracts.profile import ProfileDocument
from panestria.contracts.profile_context import ProfileSelectionRequest
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.policy import PolicyService
from panestria.kernel.repositories.policy import current_policy
from panestria.kernel.uow import UnitOfWork
from panestria.memory.profile import ProfileContext
from panestria.policy.profiles import CertificateStore

STYLE = "SYNTHETIC_STYLE_世界: prefer plain language"
PRIVATE = "SYNTHETIC_UNSELECTED_SENSITIVE_NOTE"


@pytest.fixture
def context(profile, r1_task, tmp_path):  # noqa: F811
    dsn, actor, handle, keys, vault = profile
    initialize(r1_task, tmp_path)
    document = ProfileDocument(
        fields={"communication": SecretStr(STYLE), "sensitive_notes": SecretStr(PRIVATE)},
        approved_for_local_context=("communication",),
    )
    with psycopg.connect(dsn) as c:
        vault.create(UnitOfWork(c), actor, handle, document, consent_ref=str(uuid4()))
    request = ProfileSelectionRequest(
        profile_id=handle.profile_id,
        expected_row_version=0,
        purpose="RESPONSE_STYLE",
        fields=("communication",),
        destination="OFFLINE_LOCAL_MODEL",
    )
    return dsn, actor, handle, keys, vault, ProfileContext(vault), request, document


def test_only_explicitly_approved_selected_fields_and_no_plaintext_persistence(context, caplog):
    dsn, actor, handle, keys, vault, compiler, request, document = context
    with psycopg.connect(dsn) as c:
        uow = UnitOfWork(c)
        before = [
            c.execute(f"SELECT count(*) FROM panestria.{table}").fetchone()
            for table in ("context_pack", "memory_source", "profile_event", "learning_record")
        ]
        selection = compiler.select(uow, actor, request)
        decoded = json.loads(selection.content.get_secret_value())
        assert decoded["fields"] == {"communication": STYLE}
        assert decoded["provenance"] == "owner_statement"
        assert selection.offline is True and selection.label == "RESTRICTED"
        assert PRIVATE not in selection.content.get_secret_value()
        assert compiler.revalidate(uow, actor, selection) == selection
        assert before == [
            c.execute(f"SELECT count(*) FROM panestria.{table}").fetchone()
            for table in ("context_pack", "memory_source", "profile_event", "learning_record")
        ]
        for table in ("context_pack", "memory_source", "profile_event", "learning_record", "profile_revision"):
            assert all(
                STYLE not in row[0] and PRIVATE not in row[0]
                for row in c.execute(f"SELECT row_to_json(t)::text FROM panestria.{table} t").fetchall()
            )
    assert STYLE not in repr(selection) + selection.model_dump_json() + request.sha256() + caplog.text


@pytest.mark.parametrize("destination", ["CLAUDE_CODE", "claude-subscription", "anthropic-api", "openai-api", "local"])
def test_remote_or_unqualified_destinations_rejected_before_keys(context, destination):
    dsn, actor, handle, keys, vault, compiler, request, document = context
    with pytest.raises(ValidationError):
        ProfileSelectionRequest.model_validate({**request.model_dump(), "destination": destination})
    keys.loads.clear()
    with psycopg.connect(dsn) as c, pytest.raises(KernelDenied, match="invalid_profile_selection"):
        compiler.select(UnitOfWork(c), actor, request.model_copy(update={"destination": destination}))
    assert keys.loads == []


def test_nonapproved_field_and_wrong_purpose_denied(context):
    dsn, actor, handle, keys, vault, compiler, request, document = context
    with pytest.raises(ValidationError):
        ProfileSelectionRequest.model_validate({**request.model_dump(), "fields": ("sensitive_notes",)})
    request = ProfileSelectionRequest.model_validate(
        {**request.model_dump(), "purpose": "OWNER_ASSISTANCE", "fields": ("sensitive_notes",)}
    )
    with psycopg.connect(dsn) as c, pytest.raises(KernelDenied, match="profile_fields_not_approved"):
        compiler.select(UnitOfWork(c), actor, request)


@pytest.mark.parametrize("change", ["correction", "rotation", "approval", "suppression", "expiry"])
def test_new_context_reflects_lifecycle_and_old_selection_is_invalidated(context, change):
    dsn, actor, handle, keys, vault, compiler, request, document = context
    with psycopg.connect(dsn) as c:
        selection = compiler.select(UnitOfWork(c), actor, request)
    expected = "version_conflict"
    with psycopg.connect(dsn) as c:
        uow = UnitOfWork(c)
        if change == "suppression":
            vault.suppress(uow, actor, handle.profile_id, 0)
            expected = "profile_suppressed"
        else:
            if change == "correction":
                document = document.model_copy(update={"fields": {"communication": SecretStr("CORRECTED")}})
            elif change == "rotation":
                handle = handle.model_copy(update={"key_id": str(uuid4())})
                keys.provision(handle)
            elif change == "approval":
                document = document.model_copy(update={"approved_for_local_context": ()})
            else:
                document = document.model_copy(
                    update={"valid_until": datetime.now(timezone.utc) - timedelta(seconds=1)}
                )
                expected = "profile_expired"
            vault.revise(uow, actor, handle, 0, document, consent_ref=str(uuid4()))
    with psycopg.connect(dsn) as c:
        uow = UnitOfWork(c)
        with pytest.raises(KernelDenied, match=expected):
            compiler.revalidate(uow, actor, selection)
        if change in {"correction", "rotation"}:
            updated = compiler.select(uow, actor, request.model_copy(update={"expected_row_version": 1}))
            assert updated.source.revision == 2
            if change == "correction":
                assert (
                    "CORRECTED" in updated.content.get_secret_value()
                    and STYLE not in updated.content.get_secret_value()
                )
        elif change == "approval":
            with pytest.raises(KernelDenied, match="profile_fields_not_approved"):
                compiler.select(uow, actor, request.model_copy(update={"expected_row_version": 1}))


def test_policy_change_revokes_revalidation_before_key_read(context, r1_task, tmp_path):
    dsn, actor, handle, keys, vault, compiler, request, document = context
    with psycopg.connect(dsn) as c:
        selection = compiler.select(UnitOfWork(c), actor, request)
    with psycopg.connect(dsn) as c:
        uow = UnitOfWork(c)
        service = PolicyService(CertificateStore(tmp_path, {}))
        old = current_policy(uow, actor)
        new = old.model_copy(
            update={
                "version": 2,
                "autonomy": AutonomyAxis(version=2, actions={**old.autonomy.actions, "read": "suggest"}),
            }
        )
        proposal = service.propose(uow, actor, r1_task["task"], new)
        service.decide(uow, actor, proposal.review_id, proposal.effect_digest, "approve")
        service.apply(uow, actor, proposal.review_id, proposal.effect_digest)
    keys.loads.clear()
    with psycopg.connect(dsn) as c, pytest.raises(KernelDenied, match="profile_policy_denied"):
        compiler.revalidate(UnitOfWork(c), actor, selection)
    assert keys.loads == []


@pytest.mark.parametrize("forgery", ["content", "source", "policy_ref", "offline", "label"])
def test_forged_selection_is_never_authoritative(context, forgery):
    dsn, actor, handle, keys, vault, compiler, request, document = context
    with psycopg.connect(dsn) as c:
        selection = compiler.select(UnitOfWork(c), actor, request)
    value = {
        "content": SecretStr("fabricated owner preference"),
        "source": None,
        "policy_ref": "old-policy",
        "offline": False,
        "label": "PUBLIC",
    }[forgery]
    with psycopg.connect(dsn) as c, pytest.raises(KernelDenied, match="profile_context_stale"):
        compiler.revalidate(UnitOfWork(c), actor, selection.model_copy(update={forgery: value}))


def test_scope_budget_and_missing_key_denials(context):
    dsn, actor, handle, keys, vault, compiler, request, document = context
    with psycopg.connect(dsn) as c:
        selection = compiler.select(UnitOfWork(c), actor, request)
    keys.loads.clear()
    with psycopg.connect(dsn) as c, pytest.raises(KernelDenied, match="not_found"):
        compiler.revalidate(UnitOfWork(c), Actor(str(uuid4()), actor.project_id), selection)
    assert keys.loads == []
    with psycopg.connect(dsn) as c, pytest.raises(KernelDenied, match="profile_context_size_limit"):
        compiler.select(UnitOfWork(c), actor, request.model_copy(update={"max_bytes": 128}))
    keys.values.clear()
    with psycopg.connect(dsn) as c, pytest.raises(KernelDenied, match="key_handle_missing"):
        compiler.select(UnitOfWork(c), actor, request)


def test_policy_identity_change_requires_new_selection_even_if_read_still_permitted(context, r1_task, tmp_path):
    dsn, actor, handle, keys, vault, compiler, request, document = context
    with psycopg.connect(dsn) as c:
        selection = compiler.select(UnitOfWork(c), actor, request)
    with psycopg.connect(dsn) as c:
        uow = UnitOfWork(c)
        service = PolicyService(CertificateStore(tmp_path, {}))
        old = current_policy(uow, actor)
        new = old.model_copy(update={"version": 2})
        proposal = service.propose(uow, actor, r1_task["task"], new)
        service.decide(uow, actor, proposal.review_id, proposal.effect_digest, "approve")
        service.apply(uow, actor, proposal.review_id, proposal.effect_digest)
    with psycopg.connect(dsn) as c:
        with pytest.raises(KernelDenied, match="profile_context_stale"):
            compiler.revalidate(UnitOfWork(c), actor, selection)
        fresh = compiler.select(UnitOfWork(c), actor, request)
        assert fresh.policy_ref != selection.policy_ref
        assert fresh.content == selection.content


def test_disabled_context_never_queries_policy_or_keys(context):
    dsn, actor, handle, keys, vault, compiler, request, document = context
    keys.loads.clear()
    vault.enabled = False
    with pytest.raises(KernelDenied, match="profile_disabled"):
        compiler.select(None, actor, request)
    assert keys.loads == []


def test_truthy_numeric_offline_flag_is_not_authority(context):
    dsn, actor, handle, keys, vault, compiler, request, document = context
    with psycopg.connect(dsn) as c:
        selection = compiler.select(UnitOfWork(c), actor, request)
        with pytest.raises(KernelDenied, match="profile_context_stale"):
            compiler.revalidate(UnitOfWork(c), actor, selection.model_copy(update={"offline": 1}))
