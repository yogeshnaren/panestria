"""Owner/project filters precede FTS ranking; corrections preserve original lineage."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import uuid4

from panestria.contracts.classification import classification_rank
from panestria.contracts.memory import MemoryObservation, MemorySubmission
from panestria.contracts.policy import DataLabel
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork
from panestria.memory.reclassification import consume_review, guard_review_policy

_LABELS = ("PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED", "PRIVATE")


@dataclass(frozen=True)
class MemoryRef:
    item_id: str
    revision_id: str
    revision: int
    row_version: int
    source_id: str
    sha256: str


@dataclass(frozen=True)
class MemoryHit:
    ref: MemoryRef
    body: str
    label: DataLabel
    pinned: bool
    rank: float
    explanation: str
    conflict_key: str | None
    source_uri: str


class MemoryService:
    def _project(self, uow: UnitOfWork, actor: Actor) -> None:
        if (
            uow.execute(
                "SELECT id FROM panestria.project WHERE id=%s AND owner_id=%s", (actor.project_id, actor.owner_id)
            ).fetchone()
            is None
        ):
            raise KernelDenied("not_found")

    def _source(
        self, uow: UnitOfWork, actor: Actor, document: MemorySubmission, review_id: str | None = None
    ) -> tuple[str, str]:
        source_id = str(uuid4())
        digest = hashlib.sha256(document.body.encode()).hexdigest()
        uow.execute(
            "INSERT INTO panestria.memory_source"
            " (id,owner_id,project_id,source_uri,body,sha256,privacy_label,consented_by,review_id)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                source_id,
                actor.owner_id,
                actor.project_id,
                document.source_uri,
                document.body,
                digest,
                document.label,
                actor.owner_id,
                review_id,
            ),
        )
        return source_id, digest

    def _revision(
        self,
        uow: UnitOfWork,
        actor: Actor,
        item_id: str,
        version: int,
        document: MemorySubmission,
        review_id: str | None = None,
    ) -> MemoryRef:
        source_id, digest = self._source(uow, actor, document, review_id)
        revision_id = str(uuid4())
        uow.execute(
            "INSERT INTO panestria.memory_revision"
            " (id,item_id,owner_id,project_id,version,source_id,body,sha256) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (revision_id, item_id, actor.owner_id, actor.project_id, version, source_id, document.body, digest),
        )
        return MemoryRef(item_id, revision_id, version, version - 1, source_id, digest)

    def add(self, uow: UnitOfWork, actor: Actor, document: MemorySubmission) -> MemoryRef:
        self._project(uow, actor)
        item_id = str(uuid4())
        uow.execute(
            "INSERT INTO panestria.memory_item"
            " (id,owner_id,project_id,kind,pinned,conflict_key,valid_from,valid_until,retain_until)"
            " VALUES (%s,%s,%s,%s,%s,%s,COALESCE(%s,clock_timestamp()),%s,%s)",
            (
                item_id,
                actor.owner_id,
                actor.project_id,
                document.kind,
                document.pinned,
                document.conflict_key,
                document.valid_from,
                document.valid_until,
                document.retain_until,
            ),
        )
        return self._revision(uow, actor, item_id, 1, document)

    def correct(
        self,
        uow: UnitOfWork,
        actor: Actor,
        item_id: str,
        expected_version: int,
        document: MemorySubmission,
        *,
        review_id: str | None = None,
    ) -> MemoryRef:
        if review_id is not None:
            guard_review_policy(uow, actor, review_id)
        row = uow.execute(
            "SELECT i.current_revision,i.row_version,s.privacy_label,i.kind,r.sha256 FROM panestria.memory_item i"
            " JOIN panestria.memory_revision r ON r.item_id=i.id AND r.version=i.current_revision"
            " JOIN panestria.memory_source s ON s.id=r.source_id"
            " WHERE i.id=%s AND i.owner_id=%s AND i.project_id=%s FOR UPDATE OF i",
            (item_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        if row[1] != expected_version:
            raise KernelDenied("version_conflict")
        if classification_rank(document.label) < classification_rank(row[2]):
            if review_id is None:
                raise KernelDenied("privacy_downgrade_requires_review")
            consume_review(uow, actor, review_id, item_id, expected_version, str(row[4]), document)
        elif review_id is not None:
            raise KernelDenied("privacy_review_not_required")
        if document.kind != row[3]:
            raise KernelDenied("memory_kind_conflict")
        ref = self._revision(uow, actor, item_id, int(row[0]) + 1, document, review_id)
        uow.execute(
            "UPDATE panestria.memory_item SET current_revision=%s,row_version=row_version+1,status='ACTIVE',"
            " pinned=%s,conflict_key=%s,valid_from=COALESCE(%s,clock_timestamp()),valid_until=%s,retain_until=%s"
            " WHERE id=%s",
            (
                ref.revision,
                document.pinned,
                document.conflict_key,
                document.valid_from,
                document.valid_until,
                document.retain_until,
                item_id,
            ),
        )
        return MemoryRef(ref.item_id, ref.revision_id, ref.revision, expected_version + 1, ref.source_id, ref.sha256)

    def suppress(self, uow: UnitOfWork, actor: Actor, item_id: str, expected_version: int) -> int:
        row = uow.execute(
            "SELECT row_version,status FROM panestria.memory_item"
            " WHERE id=%s AND owner_id=%s AND project_id=%s FOR UPDATE",
            (item_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        if row[0] != expected_version:
            raise KernelDenied("version_conflict")
        if row[1] == "SUPPRESSED":
            return int(row[0])
        uow.execute(
            "UPDATE panestria.memory_item SET status='SUPPRESSED',row_version=row_version+1 WHERE id=%s", (item_id,)
        )
        return expected_version + 1

    def search(
        self,
        uow: UnitOfWork,
        actor: Actor,
        query: str,
        *,
        limit: int = 10,
        allowed_labels: tuple[DataLabel, ...] = ("PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED", "PRIVATE"),
    ) -> list[MemoryHit]:
        self._project(uow, actor)
        if not query or len(query.encode()) > 4096 or not 1 <= limit <= 20 or not allowed_labels:
            raise KernelDenied("invalid_memory_query")
        if any(label not in _LABELS for label in allowed_labels):
            raise KernelDenied("invalid_classification")
        rows = uow.execute(
            "WITH scoped AS MATERIALIZED ("
            " SELECT i.*,r.id revision_id,r.body,r.sha256,r.source_id,r.search_document,s.privacy_label,s.source_uri"
            " FROM panestria.memory_item i JOIN panestria.memory_revision r"
            " ON r.item_id=i.id AND r.version=i.current_revision"
            " JOIN panestria.memory_source s ON s.id=r.source_id"
            " WHERE i.owner_id=%s AND i.project_id=%s AND i.status='ACTIVE'"
            " AND i.valid_from<=clock_timestamp() AND (i.valid_until IS NULL OR i.valid_until>clock_timestamp())"
            " AND (i.retain_until IS NULL OR i.retain_until>clock_timestamp()) AND s.privacy_label=ANY(%s))"
            " SELECT id::text,revision_id::text,current_revision,row_version,source_id::text,sha256,body,"
            " privacy_label,pinned,COALESCE(ts_rank_cd(search_document,websearch_to_tsquery('english',"
            " array_to_string(tsvector_to_array(to_tsvector('english',%s)),' OR '))),0),"
            " conflict_key,source_uri,count(*) FILTER (WHERE pinned) OVER ()"
            " FROM scoped WHERE pinned OR search_document @@ websearch_to_tsquery('english',"
            " array_to_string(tsvector_to_array(to_tsvector('english',%s)),' OR '))"
            " ORDER BY pinned DESC,10 DESC,id LIMIT %s",
            (actor.owner_id, actor.project_id, list(allowed_labels), query, query, limit),
        ).fetchall()
        if rows and int(rows[0][12]) > limit:
            raise KernelDenied("pinned_memory_limit")
        return [
            MemoryHit(
                MemoryRef(str(r[0]), str(r[1]), int(r[2]), int(r[3]), str(r[4]), str(r[5]).strip()),
                str(r[6]),
                r[7],
                bool(r[8]),
                float(r[9]),
                "owner_pin" if r[8] else "project_fts_match",
                r[10],
                str(r[11]),
            )
            for r in rows
        ]

    def record_usage(
        self,
        uow: UnitOfWork,
        actor: Actor,
        ref: MemoryRef,
        observation: MemoryObservation,
        *,
        context_pack_id: str | None = None,
    ) -> str:
        row = uow.execute(
            "SELECT 1 FROM panestria.memory_revision WHERE id=%s AND item_id=%s AND owner_id=%s AND project_id=%s",
            (ref.revision_id, ref.item_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        event_id = str(uuid4())
        uow.execute(
            "INSERT INTO panestria.memory_use_event"
            " (id,owner_id,project_id,item_id,revision_id,context_pack_id,stage,observer_kind,"
            " observer_id,confidence,evidence_ref)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                event_id,
                actor.owner_id,
                actor.project_id,
                ref.item_id,
                ref.revision_id,
                context_pack_id,
                observation.stage,
                observation.observer_kind,
                observation.observer_id,
                observation.confidence,
                observation.evidence_ref,
            ),
        )
        return event_id

    def history(self, uow: UnitOfWork, actor: Actor, item_id: str, *, after_revision: int = 0) -> dict[str, object]:
        if after_revision < 0:
            raise KernelDenied("invalid_revision")
        row = uow.execute(
            "SELECT status,row_version,current_revision FROM panestria.memory_item"
            " WHERE id=%s AND owner_id=%s AND project_id=%s",
            (item_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        revisions = uow.execute(
            "SELECT r.id::text,r.version,r.source_id::text,r.body,r.sha256,s.privacy_label,"
            " s.source_uri,s.review_id::text"
            " FROM panestria.memory_revision r JOIN panestria.memory_source s ON s.id=r.source_id"
            " WHERE r.item_id=%s AND r.owner_id=%s AND r.project_id=%s AND r.version>%s ORDER BY r.version LIMIT 100",
            (item_id, actor.owner_id, actor.project_id, after_revision),
        ).fetchall()
        return {
            "item_id": item_id,
            "state": row[0],
            "row_version": row[1],
            "current_revision": row[2],
            "revisions": [
                dict(
                    revision_id=r[0],
                    revision=r[1],
                    source_id=r[2],
                    body=r[3],
                    sha256=r[4],
                    label=r[5],
                    source_uri=r[6],
                    review_id=r[7],
                )
                for r in revisions
            ],
        }
