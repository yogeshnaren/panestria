"""Trusted-controller source metadata and protected bytes; never fetch or claim authority."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from psycopg.errors import ForeignKeyViolation
from psycopg.pq import TransactionStatus
from pydantic import ValidationError

from panestria.contracts.build import canonical_sha256
from panestria.contracts.classification import CanonicalClass, classification_rank
from panestria.contracts.research import ResearchArtifactRef, SourceSnapshotEvidence
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.research_blobs import ResearchBlobStore, ResearchBlobUnavailable
from panestria.kernel.uow import UnitOfWork


@dataclass(frozen=True)
class SourceRecordReceipt:
    snapshot_id: str
    body_sha256: str
    seq: int
    replayed: bool


@dataclass(frozen=True)
class StoredSourceRecord:
    evidence: SourceSnapshotEvidence = field(repr=False)
    body_sha256: str
    seq: int
    provenance: Literal["METADATA_ONLY_FETCH_AUTHORITY_REQUIRED"] = "METADATA_ONLY_FETCH_AUTHORITY_REQUIRED"


@dataclass(frozen=True)
class StoredSourceBytes:
    snapshot_id: str
    role: Literal["raw", "text"]
    sha256: str
    data: bytes = field(repr=False)
    privacy_label: CanonicalClass
    provenance: Literal["RETAINED_BYTES_FETCH_AUTHORITY_REQUIRED"] = "RETAINED_BYTES_FETCH_AUTHORITY_REQUIRED"


def _references(evidence: SourceSnapshotEvidence) -> list[tuple[str, int, ResearchArtifactRef]]:
    snapshot = evidence.snapshot
    refs = [(name, 0, ref) for name, ref in (
        ("raw", snapshot.raw), ("text", snapshot.text),
        ("fetch", evidence.fetch_receipt), ("reader", evidence.reader_receipt),
    ) if ref is not None]
    refs.extend(("redirect", index, ref) for index, ref in enumerate(snapshot.redirect_receipts))
    return refs


class SourceRecordService:
    def commit(self, uow: UnitOfWork, actor: Actor, evidence: SourceSnapshotEvidence) -> SourceRecordReceipt:
        if uow.connection.autocommit and uow.connection.info.transaction_status != TransactionStatus.INTRANS:
            raise KernelDenied("research_caller_transaction_required")
        try:
            evidence = SourceSnapshotEvidence.model_validate(evidence)
        except ValidationError:
            raise KernelDenied("invalid_source_record") from None
        snapshot, scope = evidence.snapshot, evidence.snapshot.scope
        if (scope.owner_id, scope.project_id) != (actor.owner_id, actor.project_id):
            raise KernelDenied("not_found")
        request = uow.execute(
            "SELECT privacy_class,max_source_bytes,max_redirects FROM panestria.research_request "
            "WHERE id=%s AND owner_id=%s AND project_id=%s AND goal_id=%s AND task_id=%s",
            (snapshot.request_id, actor.owner_id, actor.project_id, scope.goal_id, scope.task_id),
        ).fetchone()
        if request is None:
            raise KernelDenied("not_found")
        if (
            classification_rank(snapshot.query_label) < classification_rank(str(request[0]))
            or snapshot.byte_limit > int(request[1])
            or len(snapshot.redirect_receipts) > int(request[2])
        ):
            raise KernelDenied("source_request_limits_or_label_mismatch")
        digest = canonical_sha256(evidence.model_dump(mode="json"))
        try:
            row = uow.execute(
                "INSERT INTO panestria.research_source_snapshot "
                "(id,request_id,owner_id,project_id,goal_id,task_id,schema_version,body,"
                "body_sha256,privacy_class,completeness) "
                "VALUES (%s,%s,%s,%s,%s,%s,1,%s::jsonb,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING seq",
                (snapshot.snapshot_id, snapshot.request_id, actor.owner_id, actor.project_id, scope.goal_id,
                 scope.task_id, evidence.model_dump_json(), digest, evidence.privacy_label, snapshot.completeness),
            ).fetchone()
            if row is None:
                old = self.read(uow, actor, snapshot.snapshot_id, request_id=snapshot.request_id, task_id=scope.task_id)
                if old.body_sha256 != digest:
                    raise KernelDenied("source_record_conflict")
                return SourceRecordReceipt(snapshot.snapshot_id, digest, old.seq, True)
            for role, index, reference in _references(evidence):
                uow.execute(
                    "INSERT INTO panestria.research_source_artifact(snapshot_id,role,ordinal,reference) "
                    "VALUES (%s,%s,%s,%s::jsonb)",
                    (snapshot.snapshot_id, role, index, reference.model_dump_json()),
                )
        except ForeignKeyViolation:
            raise KernelDenied("source_artifact_or_scope_mismatch") from None
        append_event(
            uow, goal_id=scope.goal_id, task_id=scope.task_id, kind="research.source.recorded", actor=actor.owner_id,
            payload={"snapshot_id": snapshot.snapshot_id, "body_sha256": digest, "completeness": snapshot.completeness},
        )
        return SourceRecordReceipt(snapshot.snapshot_id, digest, int(row[0]), False)

    def read(
        self, uow: UnitOfWork, actor: Actor, snapshot_id: str, *, request_id: str, task_id: str,
    ) -> StoredSourceRecord:
        row = uow.execute(
            "SELECT body,body_sha256,seq,privacy_class FROM panestria.research_source_snapshot "
            "WHERE id=%s AND request_id=%s AND task_id=%s AND owner_id=%s AND project_id=%s",
            (snapshot_id, request_id, task_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        try:
            # JSON-mode parsing restores tuples/datetimes under the strict contract.
            evidence = SourceSnapshotEvidence.model_validate_json(json.dumps(row[0]))
            snap, scope = evidence.snapshot, evidence.snapshot.scope
            if (
                (snap.snapshot_id, snap.request_id, scope.task_id, scope.owner_id, scope.project_id)
                != (snapshot_id, request_id, task_id, actor.owner_id, actor.project_id)
                or canonical_sha256(evidence.model_dump(mode="json")) != str(row[1]).strip()
                or evidence.privacy_label != row[3]
            ):
                raise ValueError
            actual = uow.execute(
                "SELECT role,ordinal,reference FROM panestria.research_source_artifact WHERE snapshot_id=%s",
                (snapshot_id,),
            ).fetchall()
            expected = {(role, index): ref.model_dump(mode="json") for role, index, ref in _references(evidence)}
            if len(actual) != len(expected) or any(expected.get((r, i)) != ref for r, i, ref in actual):
                raise ValueError
        except (ValidationError, ValueError, TypeError, KeyError):
            raise KernelDenied("corrupt_source_metadata") from None
        return StoredSourceRecord(evidence, str(row[1]).strip(), int(row[2]))

    def read_bytes(
        self, uow: UnitOfWork, actor: Actor, snapshot_id: str, *, request_id: str, task_id: str,
        root: Path, role: Literal["raw", "text"],
    ) -> StoredSourceBytes:
        if role not in {"raw", "text"}:
            raise KernelDenied("invalid_source_role")
        record = self.read(uow, actor, snapshot_id, request_id=request_id, task_id=task_id)
        reference = record.evidence.snapshot.raw if role == "raw" else record.evidence.snapshot.text
        if reference is None:
            raise KernelDenied("missing_source_bytes")
        try:
            with ResearchBlobStore(root, actor) as store:
                raw = store.read(reference.sha256, expected_size=reference.size_bytes)
        except (ResearchBlobUnavailable, OSError):
            raise KernelDenied("source_bytes_unavailable") from None
        return StoredSourceBytes(snapshot_id, role, reference.sha256, raw, record.evidence.privacy_label)
