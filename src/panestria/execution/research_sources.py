"""Trusted retention of already-admitted observations; no network or model/tool authority."""

from __future__ import annotations

import hashlib
import os
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import uuid4, uuid5

from psycopg.pq import TransactionStatus
from pydantic import SecretStr

from panestria.brokers.research import fetch, pdf_worker, reader_worker
from panestria.brokers.research.fetch import FetchObservation, https_target
from panestria.brokers.research.pdf_bundle import PYPDF_BUNDLE_SHA256
from panestria.brokers.research.reader import ReaderObservation
from panestria.contracts.classification import CanonicalClass, derive_classification
from panestria.contracts.research import (
    PassageRef,
    ResearchArtifactRef,
    ResearchScope,
    SourceSnapshotEvidence,
    SourceSnapshotRecord,
)
from panestria.contracts.research_provenance import (
    RetainedFetchHop,
    RetainedFetchReceipt,
    RetainedReaderReceipt,
    SourceCaptureProof,
)
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.research_blobs import ResearchBlobStore
from panestria.kernel.research_sources import SourceRecordReceipt, SourceRecordService
from panestria.kernel.uow import UnitOfWork
from panestria.sandbox.egress import _public_unicast
from panestria.sandbox.profiles import SandboxProfile
from panestria.verification.research_text import validate_passage_bytes


@dataclass(frozen=True)
class ResolvedSourcePassage:
    reference: PassageRef
    text: SecretStr
    privacy_label: CanonicalClass
    limitations: tuple[str, ...]
    verdict: Literal["EVIDENCE_PRESENT"] = "EVIDENCE_PRESENT"


def _bytes(model: RetainedFetchReceipt | RetainedReaderReceipt | RetainedFetchHop | SourceCaptureProof) -> bytes:
    return model.model_dump_json().encode()


def _validate_fetch(receipt: RetainedFetchReceipt) -> None:
    https_target(receipt.requested_url)
    https_target(receipt.terminal_url)
    if (
        receipt.observed_at.tzinfo is None
        or receipt.observed_at.utcoffset() is None
        or receipt.hops[0].url_sha256 != hashlib.sha256(receipt.requested_url.encode()).hexdigest()
        or receipt.hops[-1].url_sha256 != hashlib.sha256(receipt.terminal_url.encode()).hexdigest()
        or receipt.hops[-1].status != receipt.status
        or any(h.status not in {301, 302, 303, 307, 308} for h in receipt.hops[:-1])
        or any(not _public_unicast(h.address) for h in receipt.hops)
    ):
        raise ValueError("source_fetch_lineage")


def _validate_text(receipt: RetainedReaderReceipt, text: bytes) -> None:
    decoded = text.decode("utf-8", errors="strict")
    if (
        not 0 < len(text) <= 512 * 1024
        or len(text) != receipt.text.size_bytes
        or hashlib.sha256(text).hexdigest() != receipt.text.sha256
        or unicodedata.unidata_version != "15.0.0"
        or unicodedata.normalize("NFC", decoded) != decoded
    ):
        raise ValueError("source_text_lineage")
    if receipt.extractor_version == "pypdf-6.20.1-text-v1":
        if receipt.pdf_bundle_sha256 != PYPDF_BUNDLE_SHA256 or receipt.tokenizer_sha256 != PYPDF_BUNDLE_SHA256:
            raise ValueError("source_pdf_bundle")
        previous = -3
        for start, end in receipt.page_spans:
            if (
                start != previous + 3
                or not start < end <= len(text)
                or (start > 0 and text[previous:start] != pdf_worker.SEPARATOR)
                or not text[start:end].decode("utf-8", errors="strict").strip()
            ):
                raise ValueError("source_pdf_page_spans")
            previous = end
        if previous != len(text):
            raise ValueError("source_pdf_page_spans")


class SourceStore:
    def __init__(self, root: Path, actor: Actor) -> None:
        self.root, self.actor = root, actor
        self.records = SourceRecordService()

    def commit_fetch(
        self,
        uow: UnitOfWork,
        *,
        request_id: str,
        task_id: str,
        fetched: FetchObservation,
        extracted: ReaderObservation,
        source_label: CanonicalClass,
    ) -> SourceRecordReceipt:
        """Controller-only: observations from actual brokers, never worker JSON or new fetch admission."""
        if uow.connection.autocommit and uow.connection.info.transaction_status != TransactionStatus.INTRANS:
            raise KernelDenied("research_caller_transaction_required")
        try:
            if type(fetched) is not FetchObservation or type(extracted) is not ReaderObservation:
                raise ValueError
            if fetched.outcome != "COMPLETE" or extracted.outcome != "COMPLETE" or extracted.text is None:
                raise ValueError
            if (
                extracted.raw_sha256 != fetched.retained_sha256
                or type(extracted.raw_size_bytes) is not int
                or extracted.raw_size_bytes != len(fetched.body)
            ):
                raise ValueError
            mime: Literal["text/plain", "text/html", "application/pdf"]
            if fetched.content_type == "text/plain":
                mime = "text/plain"
            elif fetched.content_type == "text/html":
                mime = "text/html"
            elif fetched.content_type == "application/pdf":
                mime = "application/pdf"
            else:
                raise ValueError
            row = uow.execute(
                "SELECT goal_id::text,privacy_class,max_source_bytes,max_redirects,max_sources,max_total_bytes "
                "FROM panestria.research_request "
                "WHERE id=%s AND task_id=%s AND owner_id=%s AND project_id=%s FOR UPDATE",
                (request_id, task_id, self.actor.owner_id, self.actor.project_id),
            ).fetchone()
            if row is None:
                raise KernelDenied("not_found")
            scope = ResearchScope(
                owner_id=self.actor.owner_id, project_id=self.actor.project_id, goal_id=str(row[0]), task_id=task_id
            )
            query_label = derive_classification((str(row[1]),)).effective
            label = derive_classification((str(row[1]), source_label)).effective
            if (
                label is None
                or query_label is None
                or source_label not in {"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"}
            ):
                raise ValueError
            if not 0 < len(fetched.body) <= int(row[2]) or not 1 <= len(fetched.hops) <= int(row[3]) + 1:
                raise ValueError
            consumed = uow.execute(
                "SELECT count(*),COALESCE(sum(a.size_bytes),0) FROM panestria.research_source_capture c "
                "JOIN panestria.research_source_snapshot s ON s.id=c.snapshot_id "
                "JOIN panestria.research_source_artifact a ON a.snapshot_id=s.id AND a.role='raw' "
                "WHERE s.request_id=%s",
                (request_id,),
            ).fetchone()
            assert consumed is not None
            if int(consumed[0]) >= int(row[4]) or int(consumed[1]) + len(fetched.body) > int(row[5]):
                raise KernelDenied("source_capture_budget_exceeded")
            identifier = uuid4()  # Never accept a model's source ID.
            text = extracted.text.get_secret_value().encode("utf-8")
            with ResearchBlobStore(self.root, self.actor) as blobs:

                def artifact(role: str, data: bytes) -> ResearchArtifactRef:
                    stored = blobs.put(data)
                    ref = ResearchArtifactRef(
                        artifact_id=str(uuid5(identifier, role)),
                        task_id=task_id,
                        sha256=stored.sha256,
                        size_bytes=stored.size_bytes,
                        privacy_label=label,
                    )
                    uow.execute(
                        "INSERT INTO panestria.artifact(id,task_id,kind,store_key,sha256,privacy_class,size_bytes) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (ref.artifact_id, task_id, "research." + role, ref.sha256, ref.sha256, label, ref.size_bytes),
                    )
                    return ref

                raw_ref, text_ref = artifact("raw", fetched.body), artifact("text", text)
                fetch_sha = hashlib.sha256(Path(fetch.__file__).read_bytes()).hexdigest()
                fetch_receipt = RetainedFetchReceipt(
                    scope=scope,
                    request_id=request_id,
                    raw=raw_ref,
                    requested_url=fetched.requested_url.get_secret_value(),
                    terminal_url=fetched.terminal_url.get_secret_value() if fetched.terminal_url else "",
                    observed_at=fetched.observed_at,
                    content_type=mime,
                    status=fetched.hops[-1].status,
                    hops=tuple(RetainedFetchHop(**h.__dict__) for h in fetched.hops),
                    adapter_sha256=fetch_sha,
                )
                _validate_fetch(fetch_receipt)
                program = pdf_worker if fetched.content_type == "application/pdf" else reader_worker
                program_path = program.__file__
                if program_path is None:
                    raise ValueError
                program_sha = hashlib.sha256(Path(program_path).read_bytes()).hexdigest()
                profile = SandboxProfile(
                    name="read-only-research",
                    uid=os.getuid(),
                    gid=os.getgid(),
                    wall_seconds=10,
                    output_bytes=1024 * 1024,
                )
                expected_extractor = {
                    "text/plain": "strict-utf8-v1",
                    "text/html": "htmlparser-text-v1",
                    "application/pdf": "pypdf-6.20.1-text-v1",
                }.get(fetched.content_type or "")
                if (
                    extracted.reader_program_sha256 != program_sha
                    or extracted.sandbox_profile_sha256 != profile.sha256()
                    or extracted.extractor_version != expected_extractor
                ):
                    raise ValueError
                reader_receipt = RetainedReaderReceipt.model_validate(
                    {
                        "scope": scope,
                        "request_id": request_id,
                        "raw": raw_ref,
                        "text": text_ref,
                        "extractor_version": extracted.extractor_version,
                        "tokenizer_sha256": extracted.tokenizer_sha256,
                        "program_sha256": extracted.reader_program_sha256,
                        "profile_sha256": extracted.sandbox_profile_sha256,
                        "effective_config_sha256": extracted.effective_config_sha256,
                        "pdf_bundle_sha256": extracted.pdf_bundle_sha256,
                        "page_spans": extracted.page_spans,
                        "limitations": extracted.limitations,
                    }
                )
                if extracted.text_sha256 != text_ref.sha256:
                    raise ValueError
                _validate_text(reader_receipt, text)
                fetched_ref = artifact("fetch", _bytes(fetch_receipt))
                reader_ref = artifact("reader", _bytes(reader_receipt))
                redirects = tuple(
                    artifact("redirect-" + str(i), _bytes(h)) for i, h in enumerate(fetch_receipt.hops[:-1])
                )
                snapshot = SourceSnapshotRecord(
                    snapshot_id=str(identifier),
                    request_id=request_id,
                    scope=scope,
                    requested_url=fetch_receipt.requested_url,
                    terminal_url=fetch_receipt.terminal_url,
                    redirect_receipts=redirects,
                    fetched_at=fetch_receipt.observed_at,
                    http_status=fetch_receipt.status,
                    content_type=fetch_receipt.content_type,
                    byte_limit=int(row[2]),
                    query_label=query_label,
                    source_label=source_label,
                    raw=raw_ref,
                    text=text_ref,
                    extractor_version=reader_receipt.extractor_version,
                    completeness="COMPLETE",
                )
                evidence = SourceSnapshotEvidence(
                    snapshot=snapshot, fetch_receipt=fetched_ref, reader_receipt=reader_ref
                )
                # The global event lock comes last, after every entity write.
                recorded, evidence = self.records._insert(uow, self.actor, evidence)
                proof = SourceCaptureProof(
                    snapshot_id=str(identifier),
                    request_id=request_id,
                    scope=scope,
                    metadata_sha256=recorded.body_sha256,
                    fetch=fetched_ref,
                    reader=reader_ref,
                    fetch_adapter_sha256=fetch_sha,
                    reader_program_sha256=program_sha,
                )
                proof_ref = artifact("proof", _bytes(proof))
                uow.execute(
                    "INSERT INTO panestria.research_source_capture(snapshot_id,task_id,metadata_sha256,"
                    "proof_artifact_id,proof_sha256,proof_size_bytes,privacy_class) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (
                        str(identifier),
                        task_id,
                        recorded.body_sha256,
                        proof_ref.artifact_id,
                        proof_ref.sha256,
                        proof_ref.size_bytes,
                        label,
                    ),
                )
                self.records._publish(uow, self.actor, evidence, recorded)
                append_event(
                    uow,
                    goal_id=scope.goal_id,
                    task_id=task_id,
                    kind="research.source.captured",
                    actor=self.actor.owner_id,
                    payload={"snapshot_id": str(identifier), "proof_sha256": proof_ref.sha256},
                )
                return recorded
        except KernelDenied:
            raise
        except Exception:
            # Caller must roll back the transaction, including any artifact rows.
            raise KernelDenied("source_capture_unconfirmed") from None

    def resolve(self, uow: UnitOfWork, reference: PassageRef, *, task_id: str) -> ResolvedSourcePassage:
        try:
            reference = PassageRef.model_validate(reference)
            record = self.records.read(
                uow, self.actor, reference.snapshot_id, request_id=reference.request_id, task_id=task_id
            )
            evidence, snapshot = record.evidence, record.evidence.snapshot
            if snapshot.completeness != "COMPLETE" or snapshot.raw is None or snapshot.text is None:
                raise ValueError
            captured = uow.execute(
                "SELECT proof_sha256,proof_size_bytes,metadata_sha256,privacy_class "
                "FROM panestria.research_source_capture "
                "WHERE snapshot_id=%s AND task_id=%s",
                (reference.snapshot_id, task_id),
            ).fetchone()
            if captured is None:
                raise KernelDenied("source_provenance_missing")
            if str(captured[2]).strip() != record.body_sha256 or captured[3] != evidence.privacy_label:
                raise ValueError
            with ResearchBlobStore(self.root, self.actor) as blobs:

                def retained(ref: ResearchArtifactRef) -> bytes:
                    return blobs.read(ref.sha256, expected_size=ref.size_bytes)

                proof = SourceCaptureProof.model_validate_json(
                    blobs.read(str(captured[0]).strip(), expected_size=int(captured[1]))
                )
                if (
                    proof.snapshot_id != snapshot.snapshot_id
                    or proof.request_id != snapshot.request_id
                    or proof.scope != snapshot.scope
                    or proof.metadata_sha256 != record.body_sha256
                    or proof.fetch != evidence.fetch_receipt
                    or proof.reader != evidence.reader_receipt
                ):
                    raise ValueError
                fetched = RetainedFetchReceipt.model_validate_json(retained(proof.fetch))
                extracted = RetainedReaderReceipt.model_validate_json(retained(proof.reader))
                if (
                    fetched.scope != snapshot.scope
                    or extracted.scope != snapshot.scope
                    or fetched.request_id != snapshot.request_id
                    or extracted.request_id != snapshot.request_id
                    or fetched.raw != snapshot.raw
                    or extracted.raw != snapshot.raw
                    or extracted.text != snapshot.text
                    or fetched.requested_url != snapshot.requested_url
                    or fetched.terminal_url != snapshot.terminal_url
                    or fetched.observed_at != snapshot.fetched_at
                    or fetched.status != snapshot.http_status
                    or fetched.content_type != snapshot.content_type
                    or extracted.extractor_version != snapshot.extractor_version
                    or fetched.adapter_sha256 != proof.fetch_adapter_sha256
                    or extracted.program_sha256 != proof.reader_program_sha256
                    or len(fetched.hops) != len(snapshot.redirect_receipts) + 1
                ):
                    raise ValueError
                _validate_fetch(fetched)
                for ref, hop in zip(snapshot.redirect_receipts, fetched.hops[:-1], strict=True):
                    if RetainedFetchHop.model_validate_json(retained(ref)) != hop:
                        raise ValueError
                retained(snapshot.raw)  # A surviving text blob cannot hide corrupt/missing raw lineage.
                text = retained(snapshot.text)
                _validate_text(extracted, text)
                matched = validate_passage_bytes(snapshot, reference, text)
                limitations = (
                    ("html-tokenizer-only", "html-layout-unverified")
                    if snapshot.content_type == "text/html"
                    else extracted.limitations
                )
                return ResolvedSourcePassage(reference, matched.text, evidence.privacy_label, limitations)
        except KernelDenied:
            raise
        except Exception:
            raise KernelDenied("source_provenance_unconfirmed") from None

    def match_quote(
        self, uow: UnitOfWork, reference: PassageRef, quote: SecretStr, *, task_id: str
    ) -> ResolvedSourcePassage:
        try:
            if type(quote) is not SecretStr or len(quote.get_secret_value().encode("utf-8")) > 512 * 1024:
                raise ValueError
            canonical_quote = unicodedata.normalize("NFC", quote.get_secret_value())
        except (ValueError, UnicodeError):
            raise KernelDenied("source_quote_mismatch") from None
        passage = self.resolve(uow, reference, task_id=task_id)
        if canonical_quote != passage.text.get_secret_value():
            raise KernelDenied("source_quote_mismatch")
        return passage
