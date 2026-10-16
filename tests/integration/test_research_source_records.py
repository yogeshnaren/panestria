"""Actual PostgreSQL/protected-byte metadata checks, never live fetch authority."""

import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest
from test_research_requests import ROOT, research  # noqa: F401 -- shared disposable DB fixture

from panestria.contracts.research import ResearchArtifactRef, SourceSnapshotEvidence, SourceSnapshotRecord
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.research_blobs import ResearchBlobStore
from panestria.kernel.research_requests import ResearchRequestService
from panestria.kernel.research_sources import SourceRecordService
from panestria.kernel.uow import UnitOfWork


@pytest.fixture
def source_record(research, tmp_path):  # noqa: F811 -- imported disposable fixture, resolved by pytest
    dsn, actor, request = research
    with psycopg.connect(dsn) as c:
        ResearchRequestService().prepare(UnitOfWork(c), actor, request)
        refs = []
        raw = b"<p>caf\xc3\xa9 and \xe4\xb8\xad\xe6\x96\x87</p>"
        text = "café and 中文".encode()
        with ResearchBlobStore(tmp_path, actor) as store:
            for kind, data in (
                ("raw", raw),
                ("text", text),
                ("fetch", b"EXPLICIT_SYNTHETIC_FETCH_NOT_AUTHORITY"),
                ("reader", b"EXPLICIT_SYNTHETIC_READER_NOT_AUTHORITY"),
            ):
                receipt = store.put(data)
                artifact = str(uuid4())
                c.execute(
                    "INSERT INTO panestria.artifact(id,task_id,kind,store_key,sha256,privacy_class,size_bytes) "
                    "VALUES (%s,%s,%s,%s,%s,'INTERNAL',%s)",
                    (artifact, request.scope.task_id, kind, receipt.sha256, receipt.sha256, receipt.size_bytes),
                )
                refs.append(
                    ResearchArtifactRef(
                        artifact_id=artifact,
                        task_id=request.scope.task_id,
                        sha256=receipt.sha256,
                        size_bytes=receipt.size_bytes,
                        privacy_label="INTERNAL",
                    )
                )
    snapshot = SourceSnapshotRecord(
        snapshot_id=str(uuid4()),
        request_id=request.request_id,
        scope=request.scope,
        requested_url="https://example.org/",
        terminal_url="https://example.org/",
        fetched_at=datetime.now(UTC),
        http_status=200,
        content_type="text/html",
        byte_limit=1024,
        query_label="INTERNAL",
        source_label="PUBLIC",
        raw=refs[0],
        text=refs[1],
        extractor_version="htmlparser-text-v1",
        completeness="COMPLETE",
    )
    evidence = SourceSnapshotEvidence(snapshot=snapshot, fetch_receipt=refs[2], reader_receipt=refs[3])
    return dsn, actor, evidence, tmp_path, raw, text


def commit(c, actor, evidence):
    return SourceRecordService().commit(UnitOfWork(c), actor, evidence)


def test_source_snapshot_and_exact_artifact_set_commit_immutably_and_retry(source_record):
    dsn, actor, evidence, root, raw, text = source_record
    with psycopg.connect(dsn) as c:
        first = commit(c, actor, evidence)
    with psycopg.connect(dsn) as c:
        again = commit(c, actor, evidence)
        assert again.replayed and again.body_sha256 == first.body_sha256 and again.seq == first.seq
        service = SourceRecordService()
        kwargs = {"request_id": evidence.snapshot.request_id, "task_id": evidence.snapshot.scope.task_id}
        stored = service.read(UnitOfWork(c), actor, first.snapshot_id, **kwargs)
        assert stored.evidence == evidence and stored.provenance == "METADATA_ONLY_FETCH_AUTHORITY_REQUIRED"
        assert "example.org" not in repr(stored)
        for role, expected in (("raw", raw), ("text", text)):
            result = service.read_bytes(UnitOfWork(c), actor, first.snapshot_id, root=root, role=role, **kwargs)
            assert result.data == expected and result.privacy_label == "INTERNAL"
            assert result.provenance == "RETAINED_BYTES_FETCH_AUTHORITY_REQUIRED"
            assert expected.decode() not in repr(result)
        rows = c.execute(
            "SELECT seq,payload FROM panestria.task_event WHERE kind='research.source.recorded'"
        ).fetchall()
        assert len(rows) == 1 and rows[0][0] > first.seq
        assert rows[0][1] == {
            "snapshot_id": first.snapshot_id,
            "body_sha256": first.body_sha256,
            "completeness": "COMPLETE",
        }
        assert c.execute("SELECT count(*) FROM panestria.research_source_artifact").fetchone() == (4,)
        for statement in (
            "UPDATE panestria.research_source_snapshot SET completeness='ERROR'",
            "DELETE FROM panestria.research_source_snapshot",
            "UPDATE panestria.research_source_artifact SET role='redirect'",
            "DELETE FROM panestria.research_source_artifact",
            "UPDATE panestria.artifact SET sha256=repeat('cd',32)",
            "DELETE FROM panestria.artifact",
        ):
            with pytest.raises(psycopg.Error), c.transaction():
                c.execute(statement)


def test_source_metadata_artifact_set_and_event_rollback_together_leaving_inert_bytes(source_record):
    dsn, actor, evidence, root, raw, _ = source_record
    with pytest.raises(RuntimeError), psycopg.connect(dsn) as c:
        commit(c, actor, evidence)
        raise RuntimeError("synthetic interruption")
    with psycopg.connect(dsn) as c:
        assert c.execute("SELECT count(*) FROM panestria.research_source_snapshot").fetchone() == (0,)
        assert c.execute("SELECT count(*) FROM panestria.research_source_artifact").fetchone() == (0,)
        assert c.execute(
            "SELECT count(*) FROM panestria.task_event WHERE kind='research.source.recorded'"
        ).fetchone() == (0,)
        with pytest.raises(KernelDenied, match="not_found"):
            SourceRecordService().read(
                UnitOfWork(c),
                actor,
                evidence.snapshot.snapshot_id,
                request_id=evidence.snapshot.request_id,
                task_id=evidence.snapshot.scope.task_id,
            )
        assert not commit(c, actor, evidence).replayed
    with ResearchBlobStore(root, actor) as store:
        assert store.read(evidence.snapshot.raw.sha256, expected_size=len(raw)) == raw


def test_source_autocommit_requires_caller_transaction(source_record):
    dsn, actor, evidence, *_ = source_record
    with psycopg.connect(dsn, autocommit=True) as c:
        with pytest.raises(KernelDenied, match="research_caller_transaction_required"):
            commit(c, actor, evidence)
        with pytest.raises(RuntimeError), c.transaction():
            commit(c, actor, evidence)
            raise RuntimeError("synthetic")
        assert c.execute("SELECT count(*) FROM panestria.research_source_snapshot").fetchone() == (0,)
        with c.transaction():
            assert not commit(c, actor, evidence).replayed


@pytest.mark.parametrize("field", ["raw", "text", "fetch_receipt", "reader_receipt", "redirect_receipts"])
def test_source_cannot_forge_any_artifact_pin(source_record, field):
    dsn, actor, evidence, *_ = source_record
    ref = evidence.fetch_receipt.model_copy(update={"sha256": "cd" * 32})
    if field in {"fetch_receipt", "reader_receipt"}:
        wrong = evidence.model_copy(update={field: ref})
    else:
        wrong = evidence.model_copy(
            update={
                "snapshot": evidence.snapshot.model_copy(
                    update={field: (ref,) if field == "redirect_receipts" else ref}
                )
            }
        )
    with pytest.raises(KernelDenied, match="source_artifact_or_scope_mismatch"), psycopg.connect(dsn) as c:
        commit(c, actor, wrong)


@pytest.mark.parametrize("field,value", [("query_label", "PUBLIC"), ("byte_limit", 2097152)])
def test_source_cannot_widen_request_classification_or_byte_budget(source_record, field, value):
    dsn, actor, evidence, *_ = source_record
    wrong = evidence.model_copy(update={"snapshot": evidence.snapshot.model_copy(update={field: value})})
    with pytest.raises(KernelDenied, match="source_request_limits_or_label_mismatch"), psycopg.connect(dsn) as c:
        commit(c, actor, wrong)


def test_source_scope_fabricated_id_and_changed_retry_are_denied(source_record):
    dsn, actor, evidence, root, *_ = source_record
    service = SourceRecordService()
    with psycopg.connect(dsn) as c:
        first = commit(c, actor, evidence)
        for change in ({"requested_url": "https://other.example.org/"}, {"extractor_version": "another-v1"}):
            with pytest.raises(KernelDenied, match="source_record_conflict"), c.transaction():
                commit(c, actor, evidence.model_copy(update={"snapshot": evidence.snapshot.model_copy(update=change)}))
        for who, identifier, req, task in (
            (
                Actor(str(uuid4()), actor.project_id),
                first.snapshot_id,
                evidence.snapshot.request_id,
                evidence.snapshot.scope.task_id,
            ),
            (
                Actor(actor.owner_id, str(uuid4())),
                first.snapshot_id,
                evidence.snapshot.request_id,
                evidence.snapshot.scope.task_id,
            ),
            (actor, str(uuid4()), evidence.snapshot.request_id, evidence.snapshot.scope.task_id),
            (actor, first.snapshot_id, str(uuid4()), evidence.snapshot.scope.task_id),
            (actor, first.snapshot_id, evidence.snapshot.request_id, str(uuid4())),
        ):
            with pytest.raises(KernelDenied, match="not_found"), c.transaction():
                service.read_bytes(UnitOfWork(c), who, identifier, root=root, role="text", request_id=req, task_id=task)
        other = evidence.snapshot.scope.model_copy(update={"goal_id": str(uuid4())})
        with pytest.raises(KernelDenied, match="not_found"), c.transaction():
            commit(
                c,
                actor,
                evidence.model_copy(update={"snapshot": evidence.snapshot.model_copy(update={"scope": other})}),
            )


def test_concurrent_source_retry_has_one_record_event_and_artifact_set(source_record):
    dsn, actor, evidence, *_ = source_record
    barrier = Barrier(2)

    def insert(_):
        barrier.wait(timeout=10)
        with psycopg.connect(dsn) as c:
            return commit(c, actor, evidence)

    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(insert, range(2)))
    assert sorted(receipt.replayed for receipt in receipts) == [False, True]
    assert len({r.seq for r in receipts}) == 1
    with psycopg.connect(dsn) as c:
        assert c.execute("SELECT count(*) FROM panestria.research_source_snapshot").fetchone() == (1,)
        assert c.execute("SELECT count(*) FROM panestria.research_source_artifact").fetchone() == (4,)
        assert c.execute(
            "SELECT count(*) FROM panestria.task_event WHERE kind='research.source.recorded'"
        ).fetchone() == (1,)


def test_changed_or_missing_protected_bytes_cannot_be_resolved(source_record):
    dsn, actor, evidence, root, *_ = source_record
    with psycopg.connect(dsn) as c:
        commit(c, actor, evidence)
        path = root / actor.owner_id / actor.project_id / evidence.snapshot.text.sha256
        path.chmod(0o600)
        path.write_bytes(b"corrupt")
        path.chmod(0o400)
        for remove in (False, True):
            if remove:
                path.unlink()
            with pytest.raises(KernelDenied, match="source_bytes_unavailable"):
                SourceRecordService().read_bytes(
                    UnitOfWork(c),
                    actor,
                    evidence.snapshot.snapshot_id,
                    root=root,
                    role="text",
                    request_id=evidence.snapshot.request_id,
                    task_id=evidence.snapshot.scope.task_id,
                )


def test_deferred_database_guard_rejects_missing_artifact_set_and_direct_null_body(source_record):
    dsn, actor, evidence, *_ = source_record
    with psycopg.connect(dsn) as c:
        commit(c, actor, evidence)
    with psycopg.connect(dsn) as c:
        row = c.execute("SELECT to_jsonb(s) FROM panestria.research_source_snapshot s").fetchone()[0]
    for malformed in (False, True):
        altered = dict(row)
        altered["id"], altered["seq"] = str(uuid4()), 900000 + int(malformed)
        altered["body"] = json.loads(json.dumps(row["body"]))
        altered["body"]["snapshot"]["snapshot_id"] = altered["id"]
        if malformed:
            del altered["body"]["fetch_receipt"]
        with pytest.raises(psycopg.errors.CheckViolation), psycopg.connect(dsn) as c:
            c.execute(
                "INSERT INTO panestria.research_source_snapshot SELECT "
                "(jsonb_populate_record(NULL::panestria.research_source_snapshot,%s::jsonb)).*",
                (json.dumps(altered, default=str),),
            )


def test_source_audit_downgrade_is_refused_without_history_loss(source_record):
    dsn, actor, evidence, *_ = source_record
    with psycopg.connect(dsn) as c:
        receipt = commit(c, actor, evidence)
    done = subprocess.run(
        [str(ROOT / ".venv/bin/alembic"), "-c", "migrations/alembic.ini", "downgrade", "0023_research_request"],
        cwd=ROOT,
        env={**os.environ, "PANESTRIA_DATABASE_URL": dsn},
        capture_output=True,
        timeout=30,
    )
    assert done.returncode != 0 and b"source snapshot audit exists" in done.stderr
    with psycopg.connect(dsn) as c:
        assert c.execute("SELECT version_num FROM alembic_version").fetchone() == ("0028_sandbox_launch_intent",)
        assert commit(c, actor, evidence).seq == receipt.seq


def test_actual_source_dump_restore_preserves_artifacts_events_and_sequence(source_record, record_property):
    import hashlib

    from psycopg import sql
    from test_memory_restore import _fixture_container

    dsn, actor, evidence, root, _, text = source_record
    with psycopg.connect(dsn) as c:
        receipt = commit(c, actor, evidence)
    container = _fixture_container()
    backup = subprocess.run(
        ["docker", "exec", container, "pg_dump", "-U", "panestria_synthetic", "-d", dsn.rsplit("/", 1)[1], "-Fc"],
        capture_output=True,
        timeout=30,
        check=True,
    )
    assert 0 < len(backup.stdout) < 8 * 1024 * 1024
    record_property("backup_sha256", hashlib.sha256(backup.stdout).hexdigest())
    name = "panestria_source_restore_" + uuid4().hex
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
            assert restored.returncode == 0, "synthetic source metadata restore failed"
            with psycopg.connect(restored_dsn) as c:
                assert commit(c, actor, evidence).seq == receipt.seq
                assert c.execute("SELECT count(*) FROM panestria.research_source_artifact").fetchone() == (4,)
                readback = SourceRecordService().read_bytes(
                    UnitOfWork(c),
                    actor,
                    receipt.snapshot_id,
                    request_id=evidence.snapshot.request_id,
                    task_id=evidence.snapshot.scope.task_id,
                    root=root,
                    role="text",
                )
                assert readback.data == text
                before = c.execute("SELECT max(seq) FROM panestria.task_event").fetchone()[0]
                version = evidence.model_copy(
                    update={"snapshot": evidence.snapshot.model_copy(update={"snapshot_id": str(uuid4())})}
                )
                following = commit(c, actor, version)
                assert not following.replayed and following.seq > before
                # Restored deferred integrity checks and immutable triggers still run.
                with pytest.raises(psycopg.Error), c.transaction():
                    c.execute("DELETE FROM panestria.research_source_artifact")
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def test_new_snapshot_versions_retain_original_and_incomplete_status(source_record):
    dsn, actor, evidence, *_ = source_record
    incomplete = evidence.model_copy(
        update={
            "snapshot": evidence.snapshot.model_copy(
                update={
                    "snapshot_id": str(uuid4()),
                    "completeness": "TRUNCATED",
                    "error_code": "size_limit",
                }
            )
        }
    )
    with psycopg.connect(dsn) as c:
        first = commit(c, actor, evidence)
        second = commit(c, actor, incomplete)
        assert first.snapshot_id != second.snapshot_id and second.seq > first.seq
    with psycopg.connect(dsn) as c:
        for stored, expected in ((first, "COMPLETE"), (second, "TRUNCATED")):
            readback = SourceRecordService().read(
                UnitOfWork(c),
                actor,
                stored.snapshot_id,
                request_id=evidence.snapshot.request_id,
                task_id=evidence.snapshot.scope.task_id,
            )
            assert readback.evidence.snapshot.completeness == expected
            assert readback.provenance == "METADATA_ONLY_FETCH_AUTHORITY_REQUIRED"
        with pytest.raises(KernelDenied, match="not_found"):
            SourceRecordService().read(
                UnitOfWork(c),
                actor,
                "model-invented-source-url",
                request_id=evidence.snapshot.request_id,
                task_id=evidence.snapshot.scope.task_id,
            )


def test_deferred_database_guard_rejects_unexpected_artifact_association(source_record):
    dsn, actor, evidence, *_ = source_record
    with psycopg.connect(dsn) as c:
        commit(c, actor, evidence)
    with pytest.raises(psycopg.errors.CheckViolation), psycopg.connect(dsn) as c:
        c.execute(
            "INSERT INTO panestria.research_source_artifact(snapshot_id,role,ordinal,reference) "
            "VALUES (%s,'redirect',0,%s::jsonb)",
            (evidence.snapshot.snapshot_id, evidence.fetch_receipt.model_dump_json()),
        )


@pytest.mark.parametrize("change", ["reader-missing", "reader-label", "scope", "version-bool"])
def test_source_closed_contract_is_revalidated_before_any_record_write(source_record, change):
    dsn, actor, evidence, *_ = source_record
    if change == "reader-missing":
        bad = evidence.model_copy(update={"reader_receipt": None})
    elif change == "reader-label":
        bad = evidence.model_copy(
            update={"reader_receipt": evidence.reader_receipt.model_copy(update={"privacy_label": "PUBLIC"})}
        )
    elif change == "scope":
        bad = evidence.model_copy(
            update={"fetch_receipt": evidence.fetch_receipt.model_copy(update={"task_id": str(uuid4())})}
        )
    else:
        bad = evidence.model_copy(update={"schema_version": True})
    with pytest.raises(KernelDenied, match="invalid_source_record"), psycopg.connect(dsn) as c:
        commit(c, actor, bad)


@pytest.mark.parametrize("mutation", ["hash", "body", "association"])
def test_readback_checks_detect_synthetic_restored_metadata_corruption(source_record, mutation):
    # Deliberate corruption in this disposable DB transaction only. Roll back the
    # test-only disabled immutable trigger along with the altered row.
    dsn, actor, evidence, *_ = source_record
    with psycopg.connect(dsn) as c:
        receipt = commit(c, actor, evidence)
    with psycopg.connect(dsn) as c:
        with pytest.raises(RuntimeError, match="rollback synthetic corruption"), c.transaction():
            if mutation == "association":
                c.execute(
                    "ALTER TABLE panestria.research_source_artifact DISABLE TRIGGER immutable_research_source_artifact"
                )
                c.execute(
                    "UPDATE panestria.research_source_artifact SET reference=%s::jsonb WHERE role='text'",
                    (evidence.fetch_receipt.model_dump_json(),),
                )
            else:
                c.execute(
                    "ALTER TABLE panestria.research_source_snapshot DISABLE TRIGGER immutable_research_source_snapshot"
                )
                if mutation == "hash":
                    c.execute("UPDATE panestria.research_source_snapshot SET body_sha256=repeat('cd',32)")
                else:
                    c.execute(
                        "UPDATE panestria.research_source_snapshot "
                        "SET body=jsonb_set(body,'{snapshot,requested_url}',to_jsonb('https://changed.example.org/'::text))"
                    )
            with pytest.raises(KernelDenied, match="corrupt_source_metadata"):
                SourceRecordService().read(
                    UnitOfWork(c),
                    actor,
                    receipt.snapshot_id,
                    request_id=evidence.snapshot.request_id,
                    task_id=evidence.snapshot.scope.task_id,
                )
            raise RuntimeError("rollback synthetic corruption")
        assert commit(c, actor, evidence).replayed
        for table in ("research_source_snapshot", "research_source_artifact"):
            with pytest.raises(psycopg.Error), c.transaction():
                c.execute(f"DELETE FROM panestria.{table}")
