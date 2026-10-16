"""Retained deterministic claim evidence, with no inference or semantic support authority."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4, uuid5

from psycopg.pq import TransactionStatus
from pydantic import ValidationError

from panestria.contracts.classification import CanonicalClass, derive_classification
from panestria.contracts.research import ResearchArtifactRef, ResearchScope
from panestria.contracts.research_claims import (
    ClaimEvidenceDraft,
    ClaimEvidenceReport,
    ClaimPassageCheck,
    RetainedClaimPayload,
)
from panestria.execution.research_sources import SourceStore
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.research_blobs import ResearchBlobStore
from panestria.kernel.research_sources import SourceRecordService
from panestria.kernel.uow import UnitOfWork


@dataclass(frozen=True)
class ClaimReceipt:
    claim_id: str
    verdict: Literal["NO_EVIDENCE", "INVALID_EVIDENCE", "EVIDENCE_PRESENT"]
    privacy_label: CanonicalClass
    report_sha256: str
    seq: int
    support_status: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"


@dataclass(frozen=True)
class VerifiedClaim:
    claim_id: str
    payload: RetainedClaimPayload = field(repr=False)
    report: ClaimEvidenceReport = field(repr=False)
    privacy_label: CanonicalClass
    historical_report_sha256: str
    current_report_sha256: str
    support_status: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"


def _payload_bytes(payload: RetainedClaimPayload) -> bytes:
    # Ordinary model_dump_json masks SecretStr. Explicit unwrap goes ONLY into
    # protected artifact bytes; never logs, events, DB metadata or model calls.
    body = payload.model_dump(mode="json")
    body["draft"]["claim"]["text"] = payload.draft.claim.text.get_secret_value()
    for item, quoted in zip(body["draft"]["quotes"], payload.draft.quotes, strict=True):
        item["quote"] = quoted.quote.get_secret_value()
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


class ClaimStore:
    def __init__(self, root: Path, actor: Actor) -> None:
        self.root, self.actor = root, actor
        self.sources = SourceStore(root, actor)

    def _assess(
        self, uow: UnitOfWork, payload: RetainedClaimPayload, digest: str, question_label: str
    ) -> ClaimEvidenceReport:
        labels = [question_label, payload.input_label]
        checks = []
        quotes = {q.reference.model_dump_json(): q.quote for q in payload.draft.quotes}
        for ordinal, ref in enumerate(payload.draft.claim.passages):
            quote = quotes.get(ref.model_dump_json())
            try:
                if ref.request_id != payload.request_id:
                    raise KernelDenied("source_request_mismatch")
                if quote is None:
                    matched = self.sources.resolve(uow, ref, task_id=payload.scope.task_id)
                else:
                    matched = self.sources.match_quote(uow, ref, quote, task_id=payload.scope.task_id)
                source = SourceRecordService().read(
                    uow, self.actor, ref.snapshot_id, request_id=payload.request_id, task_id=payload.scope.task_id
                )
                labels.append(matched.privacy_label)
                checks.append(
                    ClaimPassageCheck(
                        ordinal=ordinal,
                        reference=ref,
                        verdict="EVIDENCE_PRESENT",
                        diagnostic="retained_passage",
                        source_metadata_sha256=source.body_sha256,
                        quote_checked=quote is not None,
                        limitations=matched.limitations,
                    )
                )
            except KernelDenied as error:
                labels.append("RESTRICTED")  # Unresolved lineage cannot be optimistically public.
                checks.append(
                    ClaimPassageCheck(
                        ordinal=ordinal,
                        reference=ref,
                        verdict="INVALID_EVIDENCE",
                        diagnostic="quote_mismatch" if error.code == "source_quote_mismatch" else "source_unavailable",
                        quote_checked=quote is not None,
                    )
                )
        label = derive_classification(labels).effective
        if label is None:
            raise KernelDenied("claim_classification_unknown")
        verdict: Literal["NO_EVIDENCE", "INVALID_EVIDENCE", "EVIDENCE_PRESENT"] = (
            "NO_EVIDENCE"
            if not checks
            else ("INVALID_EVIDENCE" if any(c.verdict == "INVALID_EVIDENCE" for c in checks) else "EVIDENCE_PRESENT")
        )
        return ClaimEvidenceReport(
            claim_id=payload.claim_id,
            request_id=payload.request_id,
            scope=payload.scope,
            payload_sha256=digest,
            verdict=verdict,
            privacy_label=label,
            checks=tuple(checks),
        )

    def record(
        self,
        uow: UnitOfWork,
        *,
        request_id: str,
        task_id: str,
        draft: ClaimEvidenceDraft,
        input_label: CanonicalClass,
    ) -> ClaimReceipt:
        if uow.connection.autocommit and uow.connection.info.transaction_status != TransactionStatus.INTRANS:
            raise KernelDenied("research_caller_transaction_required")
        try:
            draft = ClaimEvidenceDraft.model_validate(draft)
            if input_label not in {"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"}:
                raise KernelDenied("claim_classification_unknown")
            row = uow.execute(
                "SELECT goal_id::text,privacy_class FROM panestria.research_request "
                "WHERE id=%s AND task_id=%s AND owner_id=%s AND project_id=%s FOR UPDATE",
                (request_id, task_id, self.actor.owner_id, self.actor.project_id),
            ).fetchone()
            if row is None:
                raise KernelDenied("not_found")
            count = uow.execute(
                "SELECT count(*) FROM panestria.research_claim WHERE request_id=%s", (request_id,)
            ).fetchone()
            assert count is not None
            if int(count[0]) >= 64:
                raise KernelDenied("claim_count_limit")
            scope = ResearchScope(
                owner_id=self.actor.owner_id, project_id=self.actor.project_id, goal_id=str(row[0]), task_id=task_id
            )
            identifier = uuid4()
            payload = RetainedClaimPayload(
                claim_id=str(identifier), request_id=request_id, scope=scope, input_label=input_label, draft=draft
            )
            raw = _payload_bytes(payload)
            if not 0 < len(raw) <= 256 * 1024:
                raise KernelDenied("claim_payload_limit")
            digest = hashlib.sha256(raw).hexdigest()
            report = self._assess(uow, payload, digest, str(row[1]))
            report_bytes = report.model_dump_json().encode()
            if len(report_bytes) > 32 * 1024:
                raise KernelDenied("claim_report_limit")
            with ResearchBlobStore(self.root, self.actor) as store:
                refs = []
                for role, data in (("claim", raw), ("claim-report", report_bytes)):
                    receipt = store.put(data)
                    ref = ResearchArtifactRef(
                        artifact_id=str(uuid5(identifier, role)),
                        task_id=task_id,
                        sha256=receipt.sha256,
                        size_bytes=receipt.size_bytes,
                        privacy_label=report.privacy_label,
                    )
                    uow.execute(
                        "INSERT INTO panestria.artifact(id,task_id,kind,store_key,sha256,privacy_class,size_bytes) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (
                            ref.artifact_id,
                            task_id,
                            "research." + role,
                            ref.sha256,
                            ref.sha256,
                            report.privacy_label,
                            ref.size_bytes,
                        ),
                    )
                    refs.append(ref)
            claim_ref, report_ref = refs
            created = uow.execute(
                "INSERT INTO panestria.research_claim(id,request_id,owner_id,project_id,goal_id,task_id,"
                "payload_artifact_id,payload_sha256,payload_size_bytes,report_artifact_id,report_sha256,report_size_bytes,"
                "privacy_class,draft_kind,verdict,verified_passage_count,support_status,verifier_version) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
                "'NOT_ASSESSED','source-citation-v1') RETURNING seq",
                (
                    str(identifier),
                    request_id,
                    self.actor.owner_id,
                    self.actor.project_id,
                    scope.goal_id,
                    task_id,
                    claim_ref.artifact_id,
                    claim_ref.sha256,
                    claim_ref.size_bytes,
                    report_ref.artifact_id,
                    report_ref.sha256,
                    report_ref.size_bytes,
                    report.privacy_label,
                    draft.claim.kind,
                    report.verdict,
                    sum(c.verdict == "EVIDENCE_PRESENT" for c in report.checks),
                ),
            ).fetchone()
            assert created is not None
            for check in report.checks:
                if check.verdict != "EVIDENCE_PRESENT":
                    continue
                passage_ref = check.reference
                uow.execute(
                    "INSERT INTO panestria.research_claim_passage(claim_id,request_id,task_id,ordinal,snapshot_id,"
                    "source_metadata_sha256,text_sha256,start_bytes,end_bytes,normalization_version,quote_matched) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        str(identifier),
                        request_id,
                        task_id,
                        check.ordinal,
                        passage_ref.snapshot_id,
                        check.source_metadata_sha256,
                        passage_ref.text_sha256,
                        passage_ref.start,
                        passage_ref.end,
                        passage_ref.normalization_version,
                        check.quote_checked,
                    ),
                )
            append_event(
                uow,
                goal_id=scope.goal_id,
                task_id=task_id,
                kind="research.claim.recorded",
                actor=self.actor.owner_id,
                payload={
                    "claim_id": str(identifier),
                    "report_sha256": report_ref.sha256,
                    "verdict": report.verdict,
                    "support_status": "NOT_ASSESSED",
                },
            )
            return ClaimReceipt(
                str(identifier), report.verdict, report.privacy_label, report_ref.sha256, int(created[0])
            )
        except KernelDenied:
            raise
        except ValidationError:
            raise KernelDenied("invalid_claim_evidence") from None
        except Exception:
            raise KernelDenied("claim_evidence_unconfirmed") from None

    def verify(self, uow: UnitOfWork, claim_id: str, *, request_id: str, task_id: str) -> VerifiedClaim:
        try:
            for identifier in (claim_id, request_id, task_id, self.actor.owner_id, self.actor.project_id):
                if type(identifier) is not str or str(UUID(identifier)) != identifier:
                    raise KernelDenied("not_found")
            row = uow.execute(
                "SELECT goal_id::text,payload_sha256,payload_size_bytes,report_sha256,report_size_bytes,privacy_class,"
                "draft_kind,verdict,support_status,verifier_version,verified_passage_count "
                "FROM panestria.research_claim "
                "WHERE id=%s AND request_id=%s AND task_id=%s AND owner_id=%s AND project_id=%s",
                (claim_id, request_id, task_id, self.actor.owner_id, self.actor.project_id),
            ).fetchone()
            if row is None:
                raise KernelDenied("not_found")
            with ResearchBlobStore(self.root, self.actor) as store:
                payload_bytes = store.read(str(row[1]).strip(), expected_size=int(row[2]))
                report_bytes = store.read(str(row[3]).strip(), expected_size=int(row[4]))
            payload = RetainedClaimPayload.model_validate_json(payload_bytes)
            report = ClaimEvidenceReport.model_validate_json(report_bytes)
            if (
                (
                    payload.claim_id,
                    payload.request_id,
                    payload.scope.owner_id,
                    payload.scope.project_id,
                    payload.scope.goal_id,
                    payload.scope.task_id,
                )
                != (claim_id, request_id, self.actor.owner_id, self.actor.project_id, str(row[0]), task_id)
                or report.claim_id != claim_id
                or report.request_id != request_id
                or report.scope != payload.scope
                or report.payload_sha256 != str(row[1]).strip()
                or _payload_bytes(payload) != payload_bytes
                or tuple(check.reference for check in report.checks) != payload.draft.claim.passages
                or any(
                    check.quote_checked != any(q.reference == check.reference for q in payload.draft.quotes)
                    for check in report.checks
                )
                or (
                    report.privacy_label,
                    payload.draft.claim.kind,
                    report.verdict,
                    report.support_status,
                    report.verifier_version,
                )
                != tuple(row[5:10])
            ):
                raise ValueError
            rows = uow.execute(
                "SELECT ordinal,snapshot_id::text,source_metadata_sha256,text_sha256,start_bytes,end_bytes,"
                "normalization_version,quote_matched FROM panestria.research_claim_passage "
                "WHERE claim_id=%s ORDER BY ordinal",
                (claim_id,),
            ).fetchall()
            expected = [
                (
                    c.ordinal,
                    c.reference.snapshot_id,
                    c.source_metadata_sha256,
                    c.reference.text_sha256,
                    c.reference.start,
                    c.reference.end,
                    c.reference.normalization_version,
                    c.quote_checked,
                )
                for c in report.checks
                if c.verdict == "EVIDENCE_PRESENT"
            ]
            actual = [(r[0], r[1], str(r[2]).strip(), str(r[3]).strip(), *r[4:]) for r in rows]
            if actual != expected or int(row[10]) != len(expected):
                raise ValueError
            question = uow.execute(
                "SELECT privacy_class FROM panestria.research_request WHERE id=%s", (request_id,)
            ).fetchone()
            assert question is not None
            current = self._assess(uow, payload, str(row[1]).strip(), str(question[0]))
            label = derive_classification((str(row[5]), current.privacy_label)).effective
            assert label is not None
            return VerifiedClaim(
                claim_id,
                payload,
                current,
                label,
                str(row[3]).strip(),
                hashlib.sha256(current.model_dump_json().encode()).hexdigest(),
            )
        except KernelDenied:
            raise
        except Exception:
            raise KernelDenied("claim_evidence_unconfirmed") from None
