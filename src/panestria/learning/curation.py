"""Canonical owner rights review; only selected PUBLIC owner originals can be packaged.

Evidence is explicitly owner-attested, never automatically interpreted as a legal
opinion or semantic qualification. No trainer/provider/memory/task promotion.
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from panestria.config_local import read_private
from panestria.contracts.build import canonical_sha256
from panestria.contracts.curation import (
    CuratedExample,
    CurationPreview,
    Eligibility,
    ExampleExport,
    ExportEntry,
    OwnerEvidence,
)
from panestria.contracts.policy import PolicyRequest
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.repositories.policy import current_policy, require_current_policy
from panestria.kernel.uow import UnitOfWork
from panestria.policy.engine import PolicyEngine


def _input(path: Path, limit: int) -> bytes:
    if not path.is_absolute() or path.resolve() != path:
        raise KernelDenied("curation_private_absolute_input_required")
    return read_private(path, limit)


def eligibility(
    example: CuratedExample, evidence: tuple[OwnerEvidence, ...], now: datetime
) -> tuple[Eligibility, tuple[str, ...]]:
    if len({e.role for e in evidence}) != len(evidence) or any(e.subject_sha256 != example.sha256() for e in evidence):
        raise KernelDenied("curation_evidence_subject_or_role_mismatch")
    if example.origin == "UNKNOWN":
        return "UNKNOWN", ("origin_requires_separate_owner_evidence",)
    if example.origin != "OWNER_AUTHORED":
        return "DENIED", ("provider_model_or_unknown_origin_not_supported",)
    if any(e.assessment == "DENIED" for e in evidence):
        return "DENIED", ("owner_evidence_denied",)
    if {e.role for e in evidence} != {"ORIGIN", "DATA_RIGHTS", "VALIDATION"}:
        return "UNKNOWN", ("separate_origin_rights_validation_evidence_required",)
    if any(e.assessment != "ALLOWED" or e.valid_until <= now for e in evidence):
        return "UNKNOWN", ("owner_evidence_unknown_or_expired",)
    by_role = {e.role: e for e in evidence}
    if (
        by_role["ORIGIN"].provider_basis != "NO_PROVIDER_OR_MODEL_INPUTS"
        or by_role["DATA_RIGHTS"].permitted_purpose != "LOCAL_TRAINING_DATA_PREPARATION"
        or by_role["VALIDATION"].validation_method != "OWNER_REVIEWED"
    ):
        return "UNKNOWN", ("explicit_provider_purpose_and_validation_basis_required",)
    return "ALLOWED", ("explicit_owner_review_and_separate_purpose_consent_still_required",)


@dataclass(frozen=True)
class Reviewed:
    preview: CurationPreview
    expires_at: datetime
    seq: int


class ExampleCuration:
    def __init__(self, actor: Actor, dsn: str):
        self.actor, self.dsn = actor, dsn

    def connect(self) -> psycopg.Connection[Any]:
        return psycopg.connect(self.dsn, connect_timeout=2, options="-c statement_timeout=3000 -c lock_timeout=1000")

    def _now(self, c: psycopg.Connection[Any]) -> datetime:
        row = c.execute("SELECT clock_timestamp()").fetchone()
        assert row is not None
        return cast(datetime, row[0])

    def _policy(self, c: psycopg.Connection[Any]) -> str:
        uow = UnitOfWork(c)
        policy = current_policy(uow, self.actor)
        ref = f"project-policy:{policy.version}:{policy.sha256()}"
        require_current_policy(uow, self.actor, ref)
        for action in ("read", "edit"):
            if (
                PolicyEngine()
                .authorize(
                    PolicyRequest(
                        owner_id=self.actor.owner_id,
                        project_id=self.actor.project_id,
                        action=action,
                        label="PUBLIC",
                        destination="local",
                        effect_digest=canonical_sha256({"purpose": "local-example-preparation"}),
                    ),
                    policy,
                )
                .outcome
                != "PERMIT"
            ):
                raise KernelDenied("curation_policy_denied")
        return ref

    def _lock(self, c: psycopg.Connection[Any]) -> None:
        c.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
            (f"curation:{self.actor.owner_id}:{self.actor.project_id}:registry",),
        )

    def _withdrawn(self, c: psycopg.Connection[Any], subject: str) -> bool:
        return (
            c.execute(
                "SELECT 1 FROM panestria.curated_example_withdrawal "
                "WHERE owner_id=%s AND project_id=%s AND content_sha256=%s",
                (self.actor.owner_id, self.actor.project_id, subject),
            ).fetchone()
            is not None
        )

    def _known_nonowner(self, c: psycopg.Connection[Any], example: CuratedExample) -> bool:
        return (
            c.execute(
                "SELECT 1 FROM panestria.curated_example_review WHERE owner_id=%s AND project_id=%s "
                "AND content_sha256=%s AND preview->'example'->>'origin' "
                "IN ('PROVIDER_OUTPUT','LOCAL_MODEL_OUTPUT') LIMIT 1",
                (self.actor.owner_id, self.actor.project_id, example.content_sha256),
            ).fetchone()
            is not None
        )

    def _prepare(
        self, c: psycopg.Connection[Any], candidate: Path, proofs: tuple[Path, ...], days: int
    ) -> CurationPreview:
        if not 0 <= len(proofs) <= 3:
            raise KernelDenied("curation_evidence_limit")
        example = CuratedExample.model_validate_json(_input(candidate, 8192))
        evidence = tuple(
            sorted((OwnerEvidence.model_validate_json(_input(p, 8192)) for p in proofs), key=lambda e: e.role)
        )
        state, reasons = eligibility(example, evidence, self._now(c))
        if self._known_nonowner(c, example):
            state, reasons = "DENIED", ("known_nonowner_lineage",)
        if self._withdrawn(c, example.content_sha256):
            state, reasons = "DENIED", ("example_withdrawn",)
        return CurationPreview(
            owner_id=UUID(self.actor.owner_id),
            project_id=UUID(self.actor.project_id),
            example=example,
            evidence=evidence,
            policy_ref=self._policy(c),
            eligibility_days=days,
            proposed_eligibility=state,
            reasons=reasons,
        )

    def prepare(self, candidate: Path, proofs: tuple[Path, ...], days: int = 7) -> dict[str, Any]:
        with self.connect() as c:
            preview = self._prepare(c, candidate, proofs, days)
        return {
            "status": "REVIEW_ONLY",
            "preview": preview.model_dump(mode="json"),
            "review_sha256": preview.sha256(),
            "example_sha256": preview.example.sha256(),
            "content_sha256": preview.example.content_sha256,
        }

    def record(
        self,
        candidate: Path,
        proofs: tuple[Path, ...],
        digest: str,
        *,
        days: int = 7,
        confirm_owner_review: bool = False,
        accept_training_data_purpose: bool = False,
    ) -> dict[str, Any]:
        if confirm_owner_review is not True:
            raise KernelDenied("curation_explicit_owner_review_required")
        with self.connect() as c:
            preview = self._prepare(c, candidate, proofs, days)
            if digest != preview.sha256():
                raise KernelDenied("curation_exact_review_required")
            subject = preview.example.sha256()
            self._lock(c)
            if self._withdrawn(c, preview.example.content_sha256):
                raise KernelDenied("curation_withdrawn")
            current_state = eligibility(preview.example, preview.evidence, self._now(c))[0]
            if self._known_nonowner(c, preview.example):
                current_state = "DENIED"
            if current_state != preview.proposed_eligibility:
                raise KernelDenied("curation_current_evidence_required")
            if preview.proposed_eligibility == "ALLOWED" and accept_training_data_purpose is not True:
                raise KernelDenied("curation_separate_training_data_purpose_required")
            prior = c.execute(
                "SELECT seq,expires_at FROM panestria.curated_example_review WHERE review_sha256=%s "
                "AND owner_id=%s AND project_id=%s",
                (digest, self.actor.owner_id, self.actor.project_id),
            ).fetchone()
            if prior is None:
                budget = c.execute(
                    "SELECT count(*),COALESCE(sum(octet_length(preview::text)),0) "
                    "FROM panestria.curated_example_review WHERE owner_id=%s AND project_id=%s",
                    (self.actor.owner_id, self.actor.project_id),
                ).fetchone()
                assert budget is not None
                if budget[0] >= 4096 or budget[1] + 32768 > 8 * 1024 * 1024:
                    raise KernelDenied("curation_registry_budget_reached")
                now = self._now(c)
                expires = min((now + timedelta(days=days), *(p.valid_until for p in preview.evidence)))
                # Unknown/denied reviews can be recorded even if a proof expired;
                # their short validity never grants an export permission.
                if expires <= now:
                    if preview.proposed_eligibility == "ALLOWED":
                        raise KernelDenied("curation_current_evidence_required")
                    expires = now + timedelta(seconds=30)
                row = c.execute(
                    "INSERT INTO panestria.curated_example_review "
                    "(review_sha256,owner_id,project_id,example_sha256,content_sha256,preview,eligibility,"
                    "purpose_consent,decided_by,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "RETURNING seq,expires_at",
                    (
                        digest,
                        self.actor.owner_id,
                        self.actor.project_id,
                        subject,
                        preview.example.content_sha256,
                        Jsonb(preview.model_dump(mode="json")),
                        preview.proposed_eligibility,
                        accept_training_data_purpose,
                        self.actor.owner_id,
                        expires,
                    ),
                ).fetchone()
                assert row is not None
                stored_expiry = row[1]
            else:
                stored_expiry = prior[1]
            latest = c.execute(
                "SELECT review_sha256 FROM panestria.curated_example_review "
                "WHERE owner_id=%s AND project_id=%s AND content_sha256=%s ORDER BY seq DESC LIMIT 1",
                (self.actor.owner_id, self.actor.project_id, preview.example.content_sha256),
            ).fetchone()
            if latest is None:
                raise KernelDenied("curation_review_missing")
            return {
                "status": "OWNER_REVIEW_RECORDED",
                "review_sha256": digest,
                "example_sha256": subject,
                "eligibility": preview.proposed_eligibility,
                "current": str(latest[0]).strip() == digest and stored_expiry > self._now(c),
                "expires_at": stored_expiry.isoformat(),
                "replayed": prior is not None,
                "assessment_source": "OWNER_ATTESTED",
                "training_started": False,
            }

    def _get(self, c: psycopg.Connection[Any], digest: str) -> Reviewed:
        row = c.execute(
            "SELECT preview,expires_at,seq,eligibility,purpose_consent,example_sha256,content_sha256 "
            "FROM panestria.curated_example_review WHERE review_sha256=%s AND owner_id=%s AND project_id=%s",
            (digest, self.actor.owner_id, self.actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        import json

        preview = CurationPreview.model_validate_json(json.dumps(row[0]))
        if (
            preview.sha256() != digest
            or str(preview.owner_id) != self.actor.owner_id
            or str(preview.project_id) != self.actor.project_id
            or preview.example.sha256() != str(row[5]).strip()
            or preview.example.content_sha256 != str(row[6]).strip()
            or preview.proposed_eligibility != row[3]
            or (row[3] == "ALLOWED" and row[4] is not True)
        ):
            raise KernelDenied("curation_review_corrupt")
        return Reviewed(preview, row[1], row[2])

    def withdraw(self, digest: str, *, confirm: bool = False) -> dict[str, Any]:
        if confirm is not True:
            raise KernelDenied("curation_explicit_withdrawal_required")
        with self.connect() as c:
            review = self._get(c, digest)
            subject = review.preview.example.content_sha256
            self._lock(c)
            c.execute(
                "INSERT INTO panestria.curated_example_withdrawal "
                "(owner_id,project_id,content_sha256,review_sha256,withdrawn_by) VALUES(%s,%s,%s,%s,%s) "
                "ON CONFLICT DO NOTHING",
                (self.actor.owner_id, self.actor.project_id, subject, digest, self.actor.owner_id),
            )
        return {
            "status": "WITHDRAWN",
            "content_sha256": subject,
            "history_deleted": False,
            "existing_exports_deleted": False,
        }

    def inspect(self, digest: str) -> dict[str, Any]:
        with self.connect() as c:
            c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            review = self._get(c, digest)
            p = review.preview
            now = self._now(c)
            policy = current_policy(UnitOfWork(c), self.actor)
            policy_current = p.policy_ref == f"project-policy:{policy.version}:{policy.sha256()}"
            latest = c.execute(
                "SELECT review_sha256 FROM panestria.curated_example_review "
                "WHERE owner_id=%s AND project_id=%s AND content_sha256=%s ORDER BY seq DESC LIMIT 1",
                (self.actor.owner_id, self.actor.project_id, p.example.content_sha256),
            ).fetchone()
            current = latest is not None and str(latest[0]).strip() == digest
            withdrawn = self._withdrawn(c, p.example.content_sha256)
            state = p.proposed_eligibility
            if withdrawn:
                state = "DENIED"
            elif not current or not policy_current or review.expires_at <= now:
                state = "UNKNOWN"
            elif state == "ALLOWED":
                state = eligibility(p.example, p.evidence, now)[0]
            return {
                "status": "REVIEW_METADATA",
                "review_sha256": digest,
                "example_sha256": p.example.sha256(),
                "content_sha256": p.example.content_sha256,
                "recorded_eligibility": p.proposed_eligibility,
                "observed_eligibility": state,
                "current_revision": current,
                "policy_current": policy_current,
                "withdrawn": withdrawn,
                "expires_at": review.expires_at.isoformat(),
                "observed_at": now.isoformat(),
                "authority": "METADATA_NOT_EXPORT_PERMISSION",
            }

    def _entries(self, c: psycopg.Connection[Any], reviews: tuple[str, ...]) -> tuple[ExportEntry, ...]:
        if not 1 <= len(reviews) <= 16 or len(set(reviews)) != len(reviews):
            raise KernelDenied("curation_export_selection_invalid")
        policy = self._policy(c)
        self._lock(c)
        found = {digest: self._get(c, digest) for digest in reviews}
        entries = []
        inputs = {}
        for digest, review in sorted(found.items()):
            p = review.preview
            subject = p.example.sha256()
            latest = c.execute(
                "SELECT review_sha256 FROM panestria.curated_example_review "
                "WHERE owner_id=%s AND project_id=%s AND content_sha256=%s ORDER BY seq DESC LIMIT 1",
                (self.actor.owner_id, self.actor.project_id, p.example.content_sha256),
            ).fetchone()
            if latest is None:
                raise KernelDenied("curation_review_missing")
            now = self._now(c)
            if (
                p.policy_ref != policy
                or p.proposed_eligibility != "ALLOWED"
                or review.expires_at <= now
                or self._withdrawn(c, p.example.content_sha256)
                or str(latest[0]).strip() != digest
                or eligibility(p.example, p.evidence, now)[0] != "ALLOWED"
            ):
                raise KernelDenied("curation_current_eligibility_required")
            if p.example.input_sha256 in inputs:
                raise KernelDenied("curation_duplicate_or_conflicting_input")
            inputs[p.example.input_sha256] = subject
            entries.append(
                ExportEntry(
                    review_sha256=digest,
                    example_sha256=subject,
                    example=p.example,
                    fold=p.example.fold,
                    evidence_sha256=tuple(canonical_sha256(e.model_dump(mode="json")) for e in p.evidence),
                    expires_at=review.expires_at,
                )
            )
        return tuple(entries)

    def export(self, reviews: tuple[str, ...], output: Path) -> dict[str, Any]:
        import os
        import stat

        # New explicit private local file; no arbitrary parent creation/overwrite.
        if not output.is_absolute() or output.resolve() != output:
            raise KernelDenied("curation_private_absolute_output_required")
        info = output.parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise KernelDenied("curation_private_output_directory_required")
        with self.connect() as c:
            packet = ExampleExport(
                owner_id=UUID(self.actor.owner_id),
                project_id=UUID(self.actor.project_id),
                created_at=self._now(c),
                entries=self._entries(c, reviews),
            )
            raw = packet.model_dump_json(indent=2).encode() + b"\n"
            if len(raw) > 128 * 1024:
                raise KernelDenied("curation_export_byte_limit")
            fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        return {
            "status": "SAVED",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "examples": len(packet.entries),
            "purpose": packet.purpose,
            "training_started": False,
        }

    def validate_export(self, path: Path) -> dict[str, Any]:
        packet = ExampleExport.model_validate_json(_input(path, 128 * 1024))
        if (str(packet.owner_id), str(packet.project_id)) != (self.actor.owner_id, self.actor.project_id):
            raise KernelDenied("not_found")
        with self.connect() as c:
            expected = self._entries(c, tuple(e.review_sha256 for e in packet.entries))
            if packet.entries != expected:
                raise KernelDenied("curation_export_lineage_mismatch")
        return {
            "status": "CURRENT_ELIGIBILITY_CONFIRMED",
            "examples": len(packet.entries),
            "training_started": False,
            "authority": "DATA_PACKET_NOT_MODEL_PROMOTION",
        }
