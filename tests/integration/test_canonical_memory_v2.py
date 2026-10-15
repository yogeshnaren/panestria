"""Canonical source/context classes and versioned owner review on real PostgreSQL."""

from __future__ import annotations

from dataclasses import replace
from itertools import product
from pathlib import Path
from uuid import uuid4

import httpx2 as httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.types.json import Jsonb
from test_aos_007 import ACTIONS, _context, _request
from test_aos_009 import _client
from test_ask_kernel import initialize
from test_classification_ledger import alembic
from test_local_provider import transport, valid_frames

from panestria.api.main import mount_ask_api
from panestria.api.routes.ask import AskApi
from panestria.contracts.ask import AskSubmission
from panestria.contracts.memory import MemorySubmission, MemorySubmissionV2
from panestria.contracts.policy import AutonomyAxis, PrivacyAxis
from panestria.inference.local import LocalProvider
from panestria.kernel.ask import AskService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork
from panestria.memory.canonical import CanonicalMemoryView
from panestria.memory.classification import MemoryClassificationService
from panestria.memory.context import ContextCompiler
from panestria.memory.service import MemoryService
from panestria.policy.engine import PolicyEngine
from panestria.resources.hardware import HardwareProbe

ARCHIVE = Path(__file__).resolve().parents[2] / "docs/specification/attachments/agentos-skills-v0.1.0.zip"
CLI = {"Authorization": "Bearer test-only-cli-token-at-least-16"}
LABELS = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED", "PRIVATE", "UNKNOWN"]


def test_canonical_policy_matrix(record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-011-TC05")
    base = _context()
    engine = PolicyEngine()
    for label, action, destination, private_flag, trust, mode in product(
        LABELS,
        ACTIONS,
        ["local", "claude-subscription", "anthropic-api", "openai-api"],
        [False, True],
        [False, True],
        ["observe", "suggest", "approve-first", "act-and-report", "act-silently"],
    ):
        context = base.model_copy(
            update={
                "trust": base.trust.model_copy(update={"allowed_actions": ACTIONS if trust else []}),
                "privacy": PrivacyAxis(
                    version=1,
                    cloud_destinations=["claude-subscription", "anthropic-api", "openai-api"],
                    allow_private_cloud=private_flag,
                ),
                "autonomy": AutonomyAxis.model_validate({"version": 1, "actions": {a: mode for a in ACTIONS}}),
            }
        )
        decision = engine.authorize(_request(context, label=label, action=action, destination=destination), context)
        if (
            label == "UNKNOWN"
            or not trust
            or mode in {"observe", "suggest"}
            or (destination != "local" and label != "PUBLIC")
        ):
            expected = "DENY"
        else:
            expected = "APPROVAL_NEEDED" if mode == "approve-first" else "PERMIT"
        assert decision.outcome == expected, (label, action, destination, private_flag, trust, mode)


@pytest.mark.parametrize("label", LABELS[:-1])
def test_canonical_source_context_and_learning(
    r1_task: dict[str, str],
    tmp_path: Path,
    label: str,
    record_property: pytest.RecordProperty,
) -> None:
    record_property("gate_case_id", "AOS-011-TC05")
    actor, _ = initialize(r1_task, tmp_path)
    data = {"body": "Pinned storage preference: PostgreSQL", "label": label, "pinned": True}
    document = (
        MemorySubmission.model_validate(data)
        if label == "PRIVATE"
        else MemorySubmissionV2.model_validate({**data, "schema_version": 2})
    )
    expected = "RESTRICTED" if label == "PRIVATE" else label
    with psycopg.connect(r1_task["dsn"]) as c:
        uow = UnitOfWork(c)
        source = MemoryService().add(uow, actor, document)
        classification = MemoryClassificationService().get(uow, actor, source.source_id)
        assert classification.original_label == label and classification.effective_label == expected
        prepared = AskService().prepare(
            uow,
            actor,
            AskSubmission(
                request_id=str(uuid4()),
                project_id=actor.project_id,
                question="What is the storage preference?",
                privacy_label="PUBLIC",
                context_tokens=4096,
            ),
        )
        assert prepared.context.sources == (source,)
        assert prepared.context.label == prepared.inference.label == expected
        ContextCompiler().revalidate(uow, actor, prepared.context)
        assert c.execute(
            "SELECT privacy_label FROM panestria.context_pack WHERE id=%s", (prepared.context.id,)
        ).fetchone() == (expected,)
        assert c.execute(
            "SELECT DISTINCT privacy_label FROM panestria.learning_record WHERE request_id=%s",
            (prepared.submission.request_id,),
        ).fetchall() == [(expected,)]
        assert CanonicalMemoryView().search(uow, actor, "PostgreSQL")[0]["label"] == expected


def api(r1_task: dict[str, str]) -> tuple[TestClient, list[httpx.Request]]:
    client = _client(r1_task)
    mocked, calls = transport(valid_frames())
    mount_ask_api(
        client.app,
        AskApi(
            LocalProvider(Path("/synthetic"), transport=mocked),
            lambda: HardwareProbe(ARCHIVE).collect(preset="omen-8gb"),
        ),
    )
    return client, calls


def test_v2_canonical_inputs_and_v1_history_compatibility(r1_task: dict[str, str], tmp_path: Path) -> None:
    initialize(r1_task, tmp_path)
    client, calls = api(r1_task)
    private = client.post("/v1/memory", json={"body": "PostgreSQL legacy note", "label": "PRIVATE"}, headers=CLI).json()
    v2 = client.get(f"/v2/memory/{private['item_id']}", headers=CLI)
    assert v2.status_code == 200 and v2.json()["schema_version"] == 2
    assert v2.json()["revisions"][0]["label"] == "RESTRICTED"
    assert v2.json()["revisions"][0]["classification"]["original_label"] == "PRIVATE"
    assert client.get(f"/v1/memory/{private['item_id']}", headers=CLI).json()["revisions"][0]["label"] == "PRIVATE"
    for label in LABELS[:4]:
        document = {"schema_version": 2, "body": "PostgreSQL canonical note", "label": label}
        added = client.post("/v2/memory", json=document, headers=CLI)
        assert added.status_code == 201 and added.json()["schema_version"] == 2
        assert client.get(f"/v2/memory/{added.json()['item_id']}", headers=CLI).json()["revisions"][0]["label"] == label
        assert client.post("/v1/memory", json=document, headers=CLI).status_code == 422
    for bad in [
        {"label": "PRIVATE"},
        {"label": "UNKNOWN"},
        {"schema_version": 1},
        {"schema_version": 2.0},
        {"approved": True},
    ]:
        document = {"schema_version": 2, "body": "Rejected PostgreSQL note", "label": "PUBLIC", **bad}
        assert client.post("/v2/memory", json=document, headers=CLI).status_code == 422
    assert (
        client.post("/v2/memory", json={"body": "missing version", "label": "PUBLIC"}, headers=CLI).status_code == 422
    )
    assert client.get("/v2/memory/search", params={"q": "PostgreSQL"}).status_code == 401
    assert client.get(f"/v2/memory/{uuid4()}", headers=CLI).status_code == 404
    assert calls == []


def test_v2_exact_review_cannot_cross_document_versions(r1_task: dict[str, str], tmp_path: Path) -> None:
    actor, _ = initialize(r1_task, tmp_path)
    client, calls = api(r1_task)
    original = client.post(
        "/v1/memory", json={"body": "Legacy private preference", "label": "PRIVATE"}, headers=CLI
    ).json()
    proposal = {
        "expected_version": 0,
        "document": {"schema_version": 2, "body": "Reviewed public summary", "label": "PUBLIC"},
    }
    review = client.post(f"/v2/memory/{original['item_id']}/privacy-review", json=proposal, headers=CLI)
    assert review.status_code == 201
    body = review.json()
    assert body["old_label"] == "RESTRICTED" and body["original_label"] == "PRIVATE"
    decision = client.post(
        f"/v2/memory-reviews/{body['review_id']}/decision",
        json={"effect_digest": body["effect_digest"], "decision": "approve"},
        headers=CLI,
    )
    assert decision.status_code == 200
    old_document = {
        **proposal,
        "document": {k: v for k, v in proposal["document"].items() if k != "schema_version"},
        "review_id": body["review_id"],
    }
    assert client.post(f"/v1/memory/{original['item_id']}/correct", json=old_document, headers=CLI).status_code == 422
    applied = client.post(
        f"/v2/memory/{original['item_id']}/correct", json={**proposal, "review_id": body["review_id"]}, headers=CLI
    )
    assert applied.status_code == 201
    history = client.get(f"/v2/memory/{original['item_id']}", headers=CLI).json()
    assert [r["label"] for r in history["revisions"]] == ["RESTRICTED", "PUBLIC"]
    assert history["revisions"][1]["classification"]["review_effect_digest"] == body["effect_digest"]
    suppressed = client.post(f"/v2/memory/{original['item_id']}/suppress", json={"expected_version": 1}, headers=CLI)
    assert suppressed.status_code == 200 and suppressed.json()["state"] == "SUPPRESSED"
    assert client.get("/v2/memory/search", params={"q": "summary"}, headers=CLI).json()["hits"] == []
    with psycopg.connect(r1_task["dsn"]) as c:
        other = Actor(str(uuid4()), actor.project_id)
        with pytest.raises(KernelDenied, match="not_found"):
            CanonicalMemoryView().history(UnitOfWork(c), other, original["item_id"])
    assert calls == []


def test_legacy_pending_pack_identity_and_false_public_context(r1_task: dict[str, str], tmp_path: Path) -> None:
    actor, _ = initialize(r1_task, tmp_path)
    compiler = ContextCompiler()
    with psycopg.connect(r1_task["dsn"]) as c:
        uow = UnitOfWork(c)
        source = MemoryService().add(
            uow, actor, MemorySubmission(body="Private PostgreSQL note", label="PRIVATE", pinned=True)
        )
        pack = compiler.compose(uow, actor, str(uuid4()), "PostgreSQL?", "PRIVATE")
        metadata = c.execute("SELECT metadata FROM panestria.context_pack WHERE id=%s", (pack.id,)).fetchone()[0]
        legacy_id = str(uuid4())
        c.execute(
            "INSERT INTO panestria.context_pack(id,owner_id,project_id,request_id,sha256,privacy_label,metadata)"
            " VALUES (%s,%s,%s,%s,%s,'PRIVATE',%s)",
            (legacy_id, actor.owner_id, actor.project_id, str(uuid4()), pack.sha256, Jsonb(metadata)),
        )
        legacy = replace(pack, id=legacy_id, label="PRIVATE")
        before = c.execute("SELECT * FROM panestria.context_pack WHERE id=%s", (legacy_id,)).fetchone()
        compiler.revalidate(uow, actor, legacy)
        assert c.execute("SELECT * FROM panestria.context_pack WHERE id=%s", (legacy_id,)).fetchone() == before
        false_id = str(uuid4())
        c.execute(
            "INSERT INTO panestria.context_pack(id,owner_id,project_id,request_id,sha256,privacy_label,metadata)"
            " VALUES (%s,%s,%s,%s,%s,'PUBLIC',%s)",
            (false_id, actor.owner_id, actor.project_id, str(uuid4()), pack.sha256, Jsonb(metadata)),
        )
        with pytest.raises(KernelDenied, match="context_classification_invalid"):
            compiler.revalidate(uow, actor, replace(pack, id=false_id, label="PUBLIC"))
        assert source.source_id == legacy.sources[0].source_id


def test_missing_classification_never_falls_back_to_public(r1_task: dict[str, str], tmp_path: Path) -> None:
    actor, _ = initialize(r1_task, tmp_path)
    with psycopg.connect(r1_task["dsn"]) as c:
        uow = UnitOfWork(c)
        ref = MemoryService().add(
            uow, actor, MemorySubmission(body="Private PostgreSQL note", label="PRIVATE", pinned=True)
        )
        c.commit()
        try:
            # Simulate an incomplete restore in this disposable fixture only.
            c.execute("SET LOCAL session_replication_role='replica'")
            c.execute("DELETE FROM panestria.memory_classification WHERE source_id=%s", (ref.source_id,))
            c.execute("SET LOCAL session_replication_role='origin'")
            with pytest.raises(KernelDenied, match="memory_classification_invalid"):
                ContextCompiler().compose(uow, actor, str(uuid4()), "PostgreSQL?", "PUBLIC")
        finally:
            c.rollback()
        assert MemoryClassificationService().get(uow, actor, ref.source_id).effective_label == "RESTRICTED"


def test_label_upgrade_preserves_legacy_rows_and_denies_data_loss(r1_database: str) -> None:
    name = "panestria_canonical_" + uuid4().hex
    dsn = r1_database.rsplit("/", 1)[0] + "/" + name
    with psycopg.connect(r1_database, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            assert alembic(dsn, "upgrade", "0018_memory_classification").returncode == 0
            owner, project = str(uuid4()), str(uuid4())
            with psycopg.connect(dsn) as c:
                c.execute("INSERT INTO panestria.principal(id,display_name) VALUES (%s,'canonical fixture')", (owner,))
                c.execute("INSERT INTO panestria.project(id,owner_id) VALUES (%s,%s)", (project, owner))
                c.execute(
                    "INSERT INTO panestria.memory_source"
                    " (id,owner_id,project_id,source_uri,body,sha256,privacy_label,consented_by)"
                    " VALUES (%s,%s,%s,'fixture','private legacy fixture',%s,'PRIVATE',%s)",
                    (str(uuid4()), owner, project, "ab" * 32, owner),
                )
                before = c.execute("SELECT * FROM panestria.memory_source ORDER BY id").fetchall()
                audit = c.execute("SELECT * FROM panestria.memory_classification ORDER BY source_id").fetchall()
            result = alembic(dsn, "upgrade", "0019_canonical_labels")
            assert result.returncode == 0, result.stderr
            with psycopg.connect(dsn) as c:
                assert c.execute("SELECT * FROM panestria.memory_source ORDER BY id").fetchall() == before
                assert c.execute("SELECT * FROM panestria.memory_classification ORDER BY source_id").fetchall() == audit
                for label in ["INTERNAL", "CONFIDENTIAL"]:
                    c.execute(
                        "INSERT INTO panestria.memory_source"
                        " (id,owner_id,project_id,source_uri,body,sha256,privacy_label,consented_by)"
                        " VALUES (%s,%s,%s,'fixture','canonical fixture',%s,%s,%s)",
                        (str(uuid4()), owner, project, "cd" * 32, label, owner),
                    )
            refused = alembic(dsn, "downgrade", "0018_memory_classification")
            assert refused.returncode != 0 and "canonical classification data exists" in refused.stderr
            with psycopg.connect(dsn) as c:
                assert c.execute("SELECT count(*) FROM panestria.memory_source").fetchone() == (3,)
                assert c.execute("SELECT version_num FROM alembic_version").fetchone() == ("0019_canonical_labels",)
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
