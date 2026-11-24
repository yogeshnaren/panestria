"""Owner/project filters precede FTS ranking; corrections preserve original lineage."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID, uuid4

from panestria.contracts.classification import classification_rank
from panestria.contracts.memory import MemoryObservation, MemorySubmission
from panestria.contracts.policy import DataLabel
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork
from panestria.memory.reclassification import consume_review, guard_review_policy

_LABELS = ("PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED", "PRIVATE")
# The default memory search page. Ask reads 20 hits, so pins written within this
# limit never make either refuse with pinned_memory_limit.
PINNED_MEMORY_LIMIT = 10
# Fixed-width stand-in for the ids a new pin has not been given yet.
_PLACEHOLDER_ID = str(UUID(int=0))
_SCOPED = (
    "SELECT i.id,r.id revision_id,i.current_revision,i.row_version,r.source_id,r.sha256,r.body,"
    "s.privacy_label,i.pinned,r.search_document,i.conflict_key,s.source_uri"
    " FROM panestria.memory_item i JOIN panestria.memory_revision r"
    " ON r.item_id=i.id AND r.version=i.current_revision"
    " JOIN panestria.memory_source s ON s.id=r.source_id"
    " WHERE i.owner_id=%s AND i.project_id=%s AND i.status='ACTIVE'"
    " AND i.valid_from<=clock_timestamp() AND (i.valid_until IS NULL OR i.valid_until>clock_timestamp())"
    " AND (i.retain_until IS NULL OR i.retain_until>clock_timestamp()) AND s.privacy_label=ANY(%s)"
)
# Pins and FTS matches are separate branches, so the FTS predicate reaches
# ix_memory_fts instead of filtering every scoped row after the fact. The tsquery
# is a bound constant, not a subquery, so the planner can estimate its matches.
_SEARCH = (
    "SELECT id::text,revision_id::text,current_revision,row_version,source_id::text,sha256,body,"
    " privacy_label,pinned,COALESCE(ts_rank_cd(search_document,%s::tsquery),0),"
    " conflict_key,source_uri,count(*) FILTER (WHERE pinned) OVER ()"
    f" FROM ({_SCOPED} AND i.pinned"
    f" UNION ALL {_SCOPED} AND NOT i.pinned AND r.owner_id=%s AND r.project_id=%s"
    " AND r.search_document @@ %s::tsquery) scoped"
    " ORDER BY pinned DESC,10 DESC,id LIMIT %s"
)


def lexeme_query(lexemes: list[str]) -> str | None:
    """OR together lexemes as quoted tsquery literals; None when there are none.

    User text only contributes lexemes, so operator syntax ("-5", "OR", quotes)
    stays plain text, and lexemes are not stemmed a second time.
    """
    quoted = ["'" + lexeme.replace("\\", "\\\\").replace("'", "''") + "'" for lexeme in lexemes]
    return " | ".join(quoted) or None


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

    def _guard_pins(self, uow: UnitOfWork, actor: Actor, item_id: str, body: str, conflict_key: str | None) -> None:
        """Refuse a pin set that the default Ask could not hold, before anything is written.

        Every pin reaches every Ask, so an oversize set would fail them all with
        pinned_context_budget_exceeded or pinned_memory_limit.
        """
        from panestria.memory import context  # context imports this module

        # Serialize pin-set changes per project; taken after any item row lock.
        uow.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
            (f"memory-pins:{actor.owner_id}:{actor.project_id}",),
        )
        # Pins not valid yet will reach Ask later, so they count now.
        rows = uow.execute(
            "SELECT r.source_id::text,r.id::text,r.sha256,r.body,i.conflict_key"
            " FROM panestria.memory_item i JOIN panestria.memory_revision r"
            " ON r.item_id=i.id AND r.version=i.current_revision"
            " WHERE i.owner_id=%s AND i.project_id=%s AND i.pinned AND i.status='ACTIVE' AND i.id<>%s"
            " AND (i.valid_until IS NULL OR i.valid_until>clock_timestamp())"
            " AND (i.retain_until IS NULL OR i.retain_until>clock_timestamp()) ORDER BY i.id",
            (actor.owner_id, actor.project_id, item_id),
        ).fetchall()
        if len(rows) >= PINNED_MEMORY_LIMIT:
            raise KernelDenied("memory_pin_limit_exceeded")
        pins = [context.reference_entry(str(r[0]), str(r[1]), str(r[2]).strip(), str(r[3]), r[4]) for r in rows]
        digest = hashlib.sha256(body.encode()).hexdigest()
        pins.append(context.reference_entry(_PLACEHOLDER_ID, _PLACEHOLDER_ID, digest, body, conflict_key))
        if context.pinned_context_bytes(pins) > context.PINNED_CONTEXT_BUDGET:
            raise KernelDenied("memory_pin_budget_exceeded")

    def add(self, uow: UnitOfWork, actor: Actor, document: MemorySubmission) -> MemoryRef:
        self._project(uow, actor)
        item_id = str(uuid4())
        if document.pinned:
            self._guard_pins(uow, actor, item_id, document.body, document.conflict_key)
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
            "SELECT i.current_revision,i.row_version,s.privacy_label,i.kind,r.sha256,i.status"
            " FROM panestria.memory_item i"
            " JOIN panestria.memory_revision r ON r.item_id=i.id AND r.version=i.current_revision"
            " JOIN panestria.memory_source s ON s.id=r.source_id"
            " WHERE i.id=%s AND i.owner_id=%s AND i.project_id=%s FOR UPDATE OF i",
            (item_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        if row[1] != expected_version:
            raise KernelDenied("version_conflict")
        if row[5] == "SUPPRESSED":
            # Correction never reactivates; the owner must unsuppress explicitly.
            raise KernelDenied("memory_suppressed")
        if classification_rank(document.label) < classification_rank(row[2]):
            if review_id is None:
                raise KernelDenied("privacy_downgrade_requires_review")
            consume_review(uow, actor, review_id, item_id, expected_version, str(row[4]), document)
        elif review_id is not None:
            raise KernelDenied("privacy_review_not_required")
        if document.kind != row[3]:
            raise KernelDenied("memory_kind_conflict")
        if document.pinned:
            self._guard_pins(uow, actor, item_id, document.body, document.conflict_key)
        ref = self._revision(uow, actor, item_id, int(row[0]) + 1, document, review_id)
        uow.execute(
            "UPDATE panestria.memory_item SET current_revision=%s,row_version=row_version+1,"
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
        return self._set_status(uow, actor, item_id, expected_version, "SUPPRESSED")

    def unsuppress(self, uow: UnitOfWork, actor: Actor, item_id: str, expected_version: int) -> int:
        """Explicitly reactivate a suppressed item; correction never does."""
        return self._set_status(uow, actor, item_id, expected_version, "ACTIVE")

    def _set_status(self, uow: UnitOfWork, actor: Actor, item_id: str, expected_version: int, status: str) -> int:
        row = uow.execute(
            "SELECT i.row_version,i.status,i.pinned,r.body,i.conflict_key FROM panestria.memory_item i"
            " JOIN panestria.memory_revision r ON r.item_id=i.id AND r.version=i.current_revision"
            " WHERE i.id=%s AND i.owner_id=%s AND i.project_id=%s FOR UPDATE OF i",
            (item_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        if row[0] != expected_version:
            raise KernelDenied("version_conflict")
        if row[1] == status:
            return int(row[0])
        if status == "ACTIVE" and row[2]:
            self._guard_pins(uow, actor, item_id, str(row[3]), row[4])
        uow.execute(
            "UPDATE panestria.memory_item SET status=%s,row_version=row_version+1 WHERE id=%s", (status, item_id)
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
        lexemes = uow.execute("SELECT tsvector_to_array(to_tsvector('english',%s))", (query,)).fetchone()
        tsquery = lexeme_query(list(lexemes[0]) if lexemes else [])
        owner, project, labels = actor.owner_id, actor.project_id, list(allowed_labels)
        rows = uow.execute(
            _SEARCH, (tsquery, owner, project, labels, owner, project, labels, owner, project, tsquery, limit)
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
