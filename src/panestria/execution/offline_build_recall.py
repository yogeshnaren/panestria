"""Exact owner-reviewed archive excerpts enter ordinary, suppressible local memory.

No inference, training, task acceptance or automatic memory promotion. Archive
integrity is checked before entering the caller-owned PostgreSQL transaction.
"""

import hashlib
import json
import re
from dataclasses import asdict
from datetime import timedelta
from typing import Any

import psycopg

from panestria.config_build import BuildSettings, _directory
from panestria.contracts.build import canonical_sha256
from panestria.contracts.goal import load_contract
from panestria.contracts.memory import MemorySubmission
from panestria.contracts.policy import PolicyRequest
from panestria.execution.offline_build import read_reference
from panestria.kernel.build import BuildEvidenceStore
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.repositories.policy import current_policy, require_current_policy
from panestria.kernel.uow import UnitOfWork
from panestria.memory.service import MemoryService
from panestria.policy.engine import PolicyEngine


def _uri(digest: str) -> str:
    if type(digest) is not str or re.fullmatch(r"[a-f0-9]{64}", digest) is None:
        raise KernelDenied("offline_recall_reference_invalid")
    return "panestria:offline-build-recall:v1:" + digest


def _excerpt(raw: bytes, limit: int) -> dict[str, object]:
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        raise KernelDenied("offline_recall_text_unavailable") from None
    prefix = text.encode()[:limit].decode("utf-8", errors="ignore")  # Only an incomplete final character is omitted.
    return {"text": prefix, "shortened": len(prefix.encode()) < len(raw)}


class OfflineBuildRecall:
    def __init__(self, settings: BuildSettings, dsn: str) -> None:
        self.settings, self.dsn = settings, dsn
        self.actor = Actor(str(settings.owner_id), str(settings.project_id))

    def connect(self) -> psycopg.Connection[Any]:
        return psycopg.connect(self.dsn, connect_timeout=2, options="-c statement_timeout=3000 -c lock_timeout=1000")

    def _document(self, digest: str, retain_days: int) -> MemorySubmission:
        uri = _uri(digest)
        if type(retain_days) is not int or not 1 <= retain_days <= 365:
            raise KernelDenied("offline_recall_retention_invalid")
        _directory(self.settings.root)
        ref = read_reference(self.settings.root, self.actor.owner_id, self.actor.project_id, digest)
        store = BuildEvidenceStore(self.settings.root / "offline-results/blobs")

        def part(name: str) -> bytes:
            selected = ref.parts[name]
            raw = b"".join(store.read_blob(sha) for sha in selected.chunks)
            if len(raw) != selected.size_bytes or hashlib.sha256(raw).hexdigest() != selected.sha256:
                raise KernelDenied("offline_recall_parts_changed")
            return raw

        contract = load_contract(json.loads(part("contract")))
        body = json.dumps(
            {
                "kind": "historical-build-reference",
                "reference_sha256": digest,
                "goal_id": str(ref.goal_id),
                "candidate_commit": ref.candidate_commit,
                "evidence_sha256": ref.evidence_sha256,
                "confirmed_at": ref.confirmed_at.isoformat(),
                "intent": _excerpt(contract.intent.encode(), 160),
                "diff": {**_excerpt(part("diff"), 256), "sha256": ref.parts["diff"].sha256},
                "historical_validation": ref.validation,
                "authority": "UNTRUSTED_REFERENCE_ONLY",
                "training_export": "DENIED",
                "local_recall_days": retain_days,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        if len(body.encode()) > 1536:
            raise KernelDenied("offline_recall_note_budget")
        return MemorySubmission(
            body=body,
            label="PUBLIC",
            pinned=False,
            kind="fact",
            source_uri=uri,
            conflict_key="offline-build:" + str(ref.goal_id),
        )

    def _policy(self, uow: UnitOfWork, document: MemorySubmission) -> str:
        policy = current_policy(uow, self.actor)
        for action in ("read", "edit"):
            decision = PolicyEngine().authorize(
                PolicyRequest(
                    owner_id=self.actor.owner_id,
                    project_id=self.actor.project_id,
                    action=action,
                    label="PUBLIC",
                    destination="local",
                    effect_digest=canonical_sha256(document.model_dump(mode="json")),
                ),
                policy,
            )
            if decision.outcome != "PERMIT":
                raise KernelDenied("offline_recall_policy_denied")
        return f"project-policy:{policy.version}:{policy.sha256()}"

    def _preview(self, document: MemorySubmission, policy_ref: str, digest: str, retain_days: int) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "owner_id": self.actor.owner_id,
            "project_id": self.actor.project_id,
            "reference_sha256": digest,
            "policy_ref": policy_ref,
            "retain_days_from_confirmation": retain_days,
            "document": document.model_dump(mode="json"),
            "purpose": "OWNER_LOCAL_REFERENCE",
            "training_export": "DENIED",
            "authority": "ORDINARY_UNTRUSTED_MEMORY_ONLY",
        }

    def prepare(self, digest: str, *, retain_days: int = 30) -> dict[str, Any]:
        document = self._document(digest, retain_days)
        with self.connect() as connection:
            preview = self._preview(document, self._policy(UnitOfWork(connection), document), digest, retain_days)
        return {"status": "REVIEW_ONLY", "preview": preview, "review_sha256": canonical_sha256(preview)}

    def remember(
        self, digest: str, review_sha256: str, *, retain_days: int = 30, accept_local_recall: bool = False
    ) -> dict[str, Any]:
        if accept_local_recall is not True:
            raise KernelDenied("explicit_local_recall_review_required")
        document = self._document(digest, retain_days)
        with self.connect() as connection:
            uow = UnitOfWork(connection)
            policy_ref = self._policy(uow, document)
            require_current_policy(uow, self.actor, policy_ref)  # Project lock precedes memory locks/creation.
            preview = self._preview(document, policy_ref, digest, retain_days)
            if review_sha256 != canonical_sha256(preview):
                raise KernelDenied("offline_recall_exact_review_required")
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (f"offline-recall:{self.actor.owner_id}:{self.actor.project_id}:{digest}",),
            )
            # Include all historical revisions so corrections/suppression/expiry
            # cannot be bypassed by creating a fresh item for the same archive.
            rows = connection.execute(
                "SELECT DISTINCT i.id::text FROM panestria.memory_item i "
                "JOIN panestria.memory_revision r ON r.item_id=i.id JOIN panestria.memory_source s ON s.id=r.source_id "
                "WHERE i.owner_id=%s AND i.project_id=%s AND s.source_uri=%s LIMIT 2",
                (self.actor.owner_id, self.actor.project_id, document.source_uri),
            ).fetchall()
            if rows:
                if len(rows) != 1:
                    raise KernelDenied("offline_recall_history_ambiguous")
                row = connection.execute(
                    "SELECT i.status,i.row_version,i.kind,i.pinned,i.valid_from<=clock_timestamp(),"
                    "(i.valid_until IS NULL OR i.valid_until>clock_timestamp()),"
                    "(i.retain_until IS NULL OR i.retain_until>clock_timestamp()),"
                    "r.id::text,r.version,r.source_id::text,r.sha256,s.privacy_label,r.body,"
                    "s.source_uri,i.retain_until "
                    "FROM panestria.memory_item i JOIN panestria.memory_revision r "
                    "ON r.item_id=i.id AND r.version=i.current_revision "
                    "JOIN panestria.memory_source s ON s.id=r.source_id WHERE i.id=%s FOR UPDATE OF i",
                    (rows[0][0],),
                ).fetchone()
                assert row is not None
                if row[0] != "ACTIVE" or row[4:7] != (True, True, True):
                    raise KernelDenied("offline_recall_suppressed_or_expired")
                if (row[2], row[3], str(row[10]).strip(), row[11], row[12], row[13]) != (
                    document.kind,
                    False,
                    hashlib.sha256(document.body.encode()).hexdigest(),
                    "PUBLIC",
                    document.body,
                    document.source_uri,
                ):
                    raise KernelDenied("offline_recall_memory_changed_requires_owner_review")
                return {
                    "status": "REMEMBERED",
                    "item_id": rows[0][0],
                    "revision_id": row[7],
                    "revision": row[8],
                    "row_version": row[1],
                    "source_id": row[9],
                    "sha256": str(row[10]).strip(),
                    "source_sha256": str(row[10]).strip(),
                    "replayed": True,
                    "retain_until": row[14].isoformat() if row[14] else None,
                    "training_export": "DENIED",
                }
            now = connection.execute("SELECT clock_timestamp()").fetchone()
            assert now is not None
            retained = document.model_copy(update={"retain_until": now[0] + timedelta(days=retain_days)})
            ref = MemoryService().add(uow, self.actor, retained)
            return {
                "status": "REMEMBERED",
                **asdict(ref),
                "source_sha256": ref.sha256,
                "replayed": False,
                "retain_until": retained.retain_until.isoformat() if retained.retain_until else None,
                "training_export": "DENIED",
            }

    def suppress(self, digest: str, item_id: str, expected_version: int, *, confirm: bool = False) -> dict[str, Any]:
        if confirm is not True:
            raise KernelDenied("explicit_local_recall_suppression_required")
        uri = _uri(digest)
        with self.connect() as connection:
            uow = UnitOfWork(connection)
            # Suppression needs no archive/model/auth/Build runtime and remains
            # possible after policy revocation; it withdraws rather than widens use.
            found = connection.execute(
                "SELECT 1 FROM panestria.memory_revision r JOIN panestria.memory_source s ON s.id=r.source_id "
                "WHERE r.item_id=%s AND r.owner_id=%s AND r.project_id=%s AND s.source_uri=%s LIMIT 1",
                (item_id, self.actor.owner_id, self.actor.project_id, uri),
            ).fetchone()
            if found is None:
                raise KernelDenied("not_found")
            version = MemoryService().suppress(uow, self.actor, item_id, expected_version)
            return {"status": "SUPPRESSED", "item_id": item_id, "row_version": version, "history_deleted": False}
