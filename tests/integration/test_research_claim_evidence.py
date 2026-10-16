"""Real PG/CAS/reader claim checks; transport is explicitly synthetic, no entailment model."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest
from pydantic import SecretStr
from test_research_requests import research  # noqa: F401 -- dependencies of imported fixtures
from test_research_source_provenance import capture, observations  # noqa: F401
from test_research_source_provenance import record as capture_source
from test_research_source_provenance import reference as source_reference
from test_research_source_records import source_record  # noqa: F401

from panestria.contracts.research import ClaimDraft, PassageRef
from panestria.contracts.research_claims import ClaimEvidenceDraft, QuotedPassage
from panestria.execution.research_claims import ClaimStore
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.research_sources import SourceRecordService
from panestria.kernel.uow import UnitOfWork


@pytest.fixture
def claim_context(capture):  # noqa: F811 -- imported disposable fixture
    dsn, actor, request, sources, pair, root = capture
    with psycopg.connect(dsn) as c:
        source = capture_source(c, request, sources, pair)
    ref = source_reference(source, request, pair)
    return dsn, actor, request, ClaimStore(root, actor), ref, pair, root


def draft(ref=None, *, text="SYNTHETIC_UNRELATED_CLAIM: the moon is cheese.", quote=None):
    return ClaimEvidenceDraft(
        claim=ClaimDraft(text=SecretStr(text), kind="FACT", passages=(ref,) if ref else ()),
        quotes=(QuotedPassage(reference=ref, quote=SecretStr(quote)),) if quote is not None else (),
    )


def record(c, request, store, candidate, label="PUBLIC"):
    return store.record(
        UnitOfWork(c), request_id=request.request_id, task_id=request.scope.task_id, draft=candidate, input_label=label
    )


def verify(c, request, store, receipt):
    return store.verify(UnitOfWork(c), receipt.claim_id, request_id=request.request_id, task_id=request.scope.task_id)


def test_retained_exact_quote_is_evidence_only_and_unrelated_claim_is_never_supported(claim_context):
    dsn, _, request, store, ref, pair, _ = claim_context
    candidate = draft(ref, quote=pair[1].text.get_secret_value().replace("é", "e\u0301"))
    with psycopg.connect(dsn) as c:
        receipt = record(c, request, store, candidate)
    with psycopg.connect(dsn) as c:
        checked = verify(c, request, store, receipt)
        assert receipt.verdict == checked.report.verdict == "EVIDENCE_PRESENT"
        assert receipt.support_status == checked.support_status == checked.report.support_status == "NOT_ASSESSED"
        assert receipt.privacy_label == checked.privacy_label == "INTERNAL"
        assert checked.payload.draft == candidate
        assert checked.report.checks[0].limitations == ("html-tokenizer-only", "html-layout-unverified")
        assert checked.current_report_sha256 == checked.historical_report_sha256
        assert "SYNTHETIC_UNRELATED_CLAIM" not in repr(checked)
        rows = c.execute("SELECT to_jsonb(c) FROM panestria.research_claim c").fetchall()
        events = c.execute("SELECT payload FROM panestria.task_event WHERE kind='research.claim.recorded'").fetchall()
        assert "SYNTHETIC_UNRELATED_CLAIM" not in json.dumps(rows + events, default=str)
        assert c.execute("SELECT count(*) FROM panestria.research_claim_passage").fetchone() == (1,)
        for table in ("research_claim", "research_claim_passage"):
            with pytest.raises(psycopg.Error), c.transaction():
                c.execute(f"DELETE FROM panestria.{table}")


def test_no_citations_remain_no_evidence_and_draft_kind_cannot_bypass_support(claim_context):
    dsn, _, request, store, _, _, _ = claim_context
    candidate = draft().model_copy(update={"claim": draft().claim.model_copy(update={"kind": "OPINION"})})
    with psycopg.connect(dsn) as c:
        receipt = record(c, request, store, candidate)
    with psycopg.connect(dsn) as c:
        checked = verify(c, request, store, receipt)
        assert checked.report.verdict == "NO_EVIDENCE" and checked.support_status == "NOT_ASSESSED"
        assert not checked.report.checks


@pytest.mark.parametrize(
    "error", ["fabricated", "wrong-hash", "out-of-range", "split-utf8", "request", "quote-case", "quote-space"]
)
def test_unresolved_or_wrong_quote_is_invalid_and_privacy_fails_closed(claim_context, error):
    dsn, _, request, store, ref, pair, _ = claim_context
    if error == "fabricated":
        ref = ref.model_copy(update={"snapshot_id": str(uuid4())})
    elif error == "wrong-hash":
        ref = ref.model_copy(update={"text_sha256": "ab" * 32})
    elif error == "out-of-range":
        ref = ref.model_copy(update={"end": ref.end + 5})
    elif error == "split-utf8":
        ref = ref.model_copy(update={"start": pair[1].text.get_secret_value().encode().find("中文".encode()) + 1})
    elif error == "request":
        ref = ref.model_copy(update={"request_id": str(uuid4())})
    text = pair[1].text.get_secret_value()
    quote = text.swapcase() if error == "quote-case" else text + " " if error == "quote-space" else None
    with psycopg.connect(dsn) as c:
        receipt = record(c, request, store, draft(ref, quote=quote))
    with psycopg.connect(dsn) as c:
        checked = verify(c, request, store, receipt)
        assert checked.report.verdict == receipt.verdict == "INVALID_EVIDENCE"
        assert checked.privacy_label == receipt.privacy_label == "RESTRICTED"
        assert checked.support_status == "NOT_ASSESSED"
        assert c.execute("SELECT count(*) FROM panestria.research_claim_passage").fetchone() == (0,)


def test_one_invalid_citation_blocks_whole_claim_while_retaining_only_verified_bindings(claim_context):
    dsn, _, request, store, ref, _, _ = claim_context
    fake = ref.model_copy(update={"snapshot_id": str(uuid4())})
    candidate = draft(ref).model_copy(update={"claim": draft(ref).claim.model_copy(update={"passages": (ref, fake)})})
    with psycopg.connect(dsn) as c:
        receipt = record(c, request, store, candidate)
    with psycopg.connect(dsn) as c:
        checked = verify(c, request, store, receipt)
        assert checked.report.verdict == "INVALID_EVIDENCE" and checked.privacy_label == "RESTRICTED"
        assert [p.verdict for p in checked.report.checks] == ["EVIDENCE_PRESENT", "INVALID_EVIDENCE"]
        assert c.execute("SELECT count(*) FROM panestria.research_claim_passage").fetchone() == (1,)


def test_metadata_only_source_cannot_create_verified_claim_binding(source_record):  # noqa: F811
    dsn, actor, evidence, root, *_ = source_record
    with psycopg.connect(dsn) as c:
        source = SourceRecordService().commit(UnitOfWork(c), actor, evidence)
    ref = PassageRef(
        snapshot_id=source.snapshot_id,
        request_id=evidence.snapshot.request_id,
        text_sha256=evidence.snapshot.text.sha256,
        start=0,
        end=2,
    )
    store = ClaimStore(root, actor)
    with psycopg.connect(dsn) as c:
        receipt = store.record(
            UnitOfWork(c),
            request_id=evidence.snapshot.request_id,
            task_id=evidence.snapshot.scope.task_id,
            draft=draft(ref),
            input_label="PUBLIC",
        )
    assert receipt.verdict == "INVALID_EVIDENCE" and receipt.privacy_label == "RESTRICTED"
    with psycopg.connect(dsn) as c:
        assert c.execute("SELECT count(*) FROM panestria.research_claim_passage").fetchone() == (0,)


@pytest.mark.parametrize("artifact", ["payload", "report"])
def test_corrupt_claim_or_report_bytes_never_verify(claim_context, artifact):
    dsn, actor, request, store, ref, _, root = claim_context
    with psycopg.connect(dsn) as c:
        receipt = record(c, request, store, draft(ref))
        column = "payload_sha256" if artifact == "payload" else "report_sha256"
        digest = str(c.execute(f"SELECT {column} FROM panestria.research_claim").fetchone()[0]).strip()
    path = root / actor.owner_id / actor.project_id / digest
    path.chmod(0o600)
    path.write_bytes(b"CORRUPT_SYNTHETIC")
    path.chmod(0o400)
    with psycopg.connect(dsn) as c, pytest.raises(KernelDenied, match="claim_evidence_unconfirmed"):
        verify(c, request, store, receipt)


def test_fresh_verification_detects_lost_source_without_rewriting_passing_history(claim_context):
    dsn, actor, request, store, ref, _, root = claim_context
    with psycopg.connect(dsn) as c:
        receipt = record(c, request, store, draft(ref))
        raw_sha = c.execute("SELECT sha256 FROM panestria.research_source_artifact WHERE role='raw'").fetchone()[0]
    (root / actor.owner_id / actor.project_id / str(raw_sha).strip()).unlink()
    with psycopg.connect(dsn) as c:
        checked = verify(c, request, store, receipt)
        assert checked.report.verdict == "INVALID_EVIDENCE" and checked.privacy_label == "RESTRICTED"
        assert checked.current_report_sha256 != checked.historical_report_sha256
        assert c.execute("SELECT verdict,report_sha256 FROM panestria.research_claim").fetchone() == (
            "EVIDENCE_PRESENT",
            receipt.report_sha256,
        )


def test_claim_scope_denial_and_atomic_rollback_leave_no_pass_or_extra_rows(claim_context):
    dsn, actor, request, store, ref, _, root = claim_context
    with pytest.raises(RuntimeError), psycopg.connect(dsn) as c:
        orphan = record(c, request, store, draft(ref))
        raise RuntimeError("synthetic failure")
    with psycopg.connect(dsn) as c:
        assert c.execute("SELECT count(*) FROM panestria.research_claim").fetchone() == (0,)
        assert c.execute("SELECT count(*) FROM panestria.research_claim_passage").fetchone() == (0,)
        assert c.execute(
            "SELECT count(*) FROM panestria.task_event WHERE kind='research.claim.recorded'"
        ).fetchone() == (0,)
        with pytest.raises(KernelDenied, match="not_found"):
            verify(c, request, store, orphan)
        receipt = record(c, request, store, draft(ref))
    for wrong in (
        ClaimStore(root, Actor(str(uuid4()), actor.project_id)),
        ClaimStore(root, Actor(actor.owner_id, str(uuid4()))),
    ):
        with psycopg.connect(dsn) as c, pytest.raises(KernelDenied, match="not_found"):
            verify(c, request, wrong, receipt)
    with (
        psycopg.connect(dsn, autocommit=True) as c,
        pytest.raises(KernelDenied, match="research_caller_transaction_required"),
    ):
        record(c, request, store, draft(ref))


def test_unknown_classification_and_revalidated_bad_contract_deny_before_claim_write(claim_context):
    dsn, _, request, store, ref, _, _ = claim_context
    for label in ("UNKNOWN", "PRIVATE"):
        with psycopg.connect(dsn) as c, pytest.raises(KernelDenied, match="claim_classification_unknown"):
            record(c, request, store, draft(ref), label=label)
    with psycopg.connect(dsn) as c, pytest.raises(KernelDenied, match="invalid_claim_evidence"):
        record(c, request, store, draft(ref).model_copy(update={"schema_version": True}))


def test_concurrent_claim_creation_cannot_oversubscribe_final_count_slot(claim_context):
    dsn, _, request, store, _, _, _ = claim_context
    for _ in range(63):
        with psycopg.connect(dsn) as c:
            record(c, request, store, draft())
    barrier = Barrier(2)

    def create(_):
        barrier.wait(timeout=10)
        try:
            with psycopg.connect(dsn) as c:
                record(c, request, store, draft())
            return "recorded"
        except KernelDenied as error:
            assert error.code == "claim_count_limit"
            return "limit"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(create, range(2))) == ["limit", "recorded"]
    with psycopg.connect(dsn) as c:
        assert c.execute("SELECT count(*) FROM panestria.research_claim").fetchone() == (64,)


def test_claim_all_entity_writes_precede_global_event_lock(claim_context):
    dsn, _, request, store, ref, _, _ = claim_context

    class EventLast(UnitOfWork):
        event_seen = False

        def execute(self, query, params=()):
            if "pg_advisory_xact_lock" in query:
                self.event_seen = True
            if self.event_seen and query.lstrip().startswith(("INSERT", "UPDATE", "DELETE")):
                assert "panestria.task_event" in query
            return super().execute(query, params)

    with psycopg.connect(dsn) as c:
        uow = EventLast(c)
        store.record(
            uow, request_id=request.request_id, task_id=request.scope.task_id, draft=draft(ref), input_label="PUBLIC"
        )
        assert uow.event_seen


def test_database_rejects_claim_scope_pin_support_and_missing_passage_forgeries(claim_context):
    dsn, _, request, store, ref, _, _ = claim_context
    with psycopg.connect(dsn) as c:
        record(c, request, store, draft(ref))
    with psycopg.connect(dsn) as c:
        original = c.execute("SELECT to_jsonb(r) FROM panestria.research_claim r").fetchone()[0]
    for kind in ("scope", "pin", "support", "missing-passage"):
        row = dict(original)
        row.update(id=str(uuid4()), seq=800000 + len(kind))
        if kind != "missing-passage":
            row.update(verdict="NO_EVIDENCE", verified_passage_count=0)
        if kind == "scope":
            row["owner_id"] = str(uuid4())
        elif kind == "pin":
            row["payload_sha256"] = "cd" * 32
        elif kind == "support":
            row["support_status"] = "SUPPORTED"
        with pytest.raises(psycopg.Error), psycopg.connect(dsn) as c:
            c.execute(
                "INSERT INTO panestria.research_claim SELECT "
                "(jsonb_populate_record(NULL::panestria.research_claim,%s::jsonb)).*",
                (json.dumps(row, default=str),),
            )


def test_claim_audit_actual_dump_restore_and_downgrade_guard(claim_context, record_property):
    import hashlib
    import os
    import subprocess

    from psycopg import sql
    from test_memory_restore import _fixture_container
    from test_research_requests import ROOT

    dsn, _, request, store, ref, _, _ = claim_context
    with psycopg.connect(dsn) as c:
        receipt = record(c, request, store, draft(ref))
    rejected = subprocess.run(
        [str(ROOT / ".venv/bin/alembic"), "-c", "migrations/alembic.ini", "downgrade", "0025_source_capture"],
        cwd=ROOT,
        env={**os.environ, "PANESTRIA_DATABASE_URL": dsn},
        capture_output=True,
        timeout=30,
    )
    assert rejected.returncode != 0 and b"claim evidence audit exists" in rejected.stderr
    container = _fixture_container()
    backup = subprocess.run(
        ["docker", "exec", container, "pg_dump", "-U", "panestria_synthetic", "-d", dsn.rsplit("/", 1)[1], "-Fc"],
        capture_output=True,
        timeout=30,
        check=True,
    )
    assert 0 < len(backup.stdout) < 8 * 1024 * 1024
    record_property("backup_sha256", hashlib.sha256(backup.stdout).hexdigest())
    name = "panestria_claim_restore_" + uuid4().hex
    restored_dsn = dsn.rsplit("/", 1)[0] + "/" + name
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            restored = subprocess.run(
                [
                    "docker",
                    "exec",
                    "-i",
                    container,
                    "pg_restore",
                    "-U",
                    "panestria_synthetic",
                    "-d",
                    name,
                    "--exit-on-error",
                ],
                input=backup.stdout,
                capture_output=True,
                timeout=30,
            )
            assert restored.returncode == 0, "synthetic claim evidence restore failed"
            with psycopg.connect(restored_dsn) as c:
                checked = verify(c, request, store, receipt)
                assert checked.report.verdict == "EVIDENCE_PRESENT" and checked.support_status == "NOT_ASSESSED"
                assert checked.current_report_sha256 == receipt.report_sha256
                before = c.execute("SELECT max(seq) FROM panestria.task_event").fetchone()[0]
                following = record(c, request, store, draft())
                assert following.seq > before and following.claim_id != receipt.claim_id
                with pytest.raises(psycopg.Error), c.transaction():
                    c.execute("DELETE FROM panestria.research_claim_passage")
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def test_copied_foreign_claim_payload_cannot_verify_under_a_new_metadata_identity(claim_context):
    dsn, _, request, store, ref, _, _ = claim_context
    with psycopg.connect(dsn) as c:
        record(c, request, store, draft(ref))
    with psycopg.connect(dsn) as c:
        original = c.execute("SELECT to_jsonb(r) FROM panestria.research_claim r").fetchone()[0]
        original.update(id=str(uuid4()), seq=900000, verdict="NO_EVIDENCE", verified_passage_count=0)
        c.execute(
            "INSERT INTO panestria.research_claim SELECT "
            "(jsonb_populate_record(NULL::panestria.research_claim,%s::jsonb)).*",
            (json.dumps(original, default=str),),
        )
    with psycopg.connect(dsn) as c, pytest.raises(KernelDenied, match="claim_evidence_unconfirmed"):
        store.verify(UnitOfWork(c), original["id"], request_id=request.request_id, task_id=request.scope.task_id)
