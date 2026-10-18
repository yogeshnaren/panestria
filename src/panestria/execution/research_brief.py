"""Connect canonical retained requests, claims and sources into an offline owner view."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from uuid import UUID

import psycopg
from pydantic import SecretStr

from panestria.contracts.build import canonical_sha256
from panestria.contracts.classification import derive_classification
from panestria.contracts.research import ResearchArtifactRef, ResearchLimits, ResearchRequestRecord, ResearchScope
from panestria.contracts.research_brief import (
    BriefCitation,
    BriefClaim,
    CollectionObservation,
    EvidenceBrief,
    FetchObservation,
    SearchObservation,
)
from panestria.execution.research_claims import ClaimStore
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.research_blobs import ResearchBlobStore
from panestria.kernel.research_sources import SourceRecordService
from panestria.kernel.uow import UnitOfWork

MAX_BRIEF_BYTES = 4 * 1024 * 1024


class RetainedBrief:
    def __init__(self, root: Path, actor: Actor) -> None:
        self.root, self.actor = root, actor

    def inspect(self, dsn: str, request_id: str, task_id: str) -> EvidenceBrief:
        try:
            for identifier in (request_id, task_id, self.actor.owner_id, self.actor.project_id):
                if type(identifier) is not str or str(UUID(identifier)) != identifier:
                    raise KernelDenied("not_found")
            with psycopg.connect(
                dsn, connect_timeout=2, options="-c statement_timeout=5000 -c lock_timeout=1000"
            ) as connection:
                # A stable canonical DB view; this reader does not claim execution authority.
                connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                return self._inspect(UnitOfWork(connection), request_id, task_id)
        except KernelDenied:
            raise
        except Exception:
            # Database errors, invalid metadata and missing question bytes reveal no raw content.
            raise KernelDenied("research_brief_unavailable") from None

    def _inspect(self, uow: UnitOfWork, request_id: str, task_id: str) -> EvidenceBrief:
        row = uow.execute(
            "SELECT r.goal_id::text,r.question_artifact_id::text,r.question_sha256,r.question_size_bytes,"
            "r.privacy_class,r.max_sources,r.max_source_bytes,r.max_total_bytes,r.max_redirects,"
            "r.deadline_seconds,r.request_sha256,t.state,g.status "
            "FROM panestria.research_request r JOIN panestria.task t ON t.id=r.task_id "
            "JOIN panestria.goal g ON g.id=t.goal_id "
            "WHERE r.id=%s AND r.task_id=%s AND r.owner_id=%s AND r.project_id=%s "
            "AND g.id=r.goal_id AND g.owner_id=r.owner_id AND g.project_id=r.project_id",
            (request_id, task_id, self.actor.owner_id, self.actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        scope = ResearchScope(
            owner_id=self.actor.owner_id, project_id=self.actor.project_id, goal_id=str(row[0]), task_id=task_id
        )
        request = ResearchRequestRecord(
            request_id=request_id,
            scope=scope,
            question=ResearchArtifactRef(
                artifact_id=str(row[1]),
                task_id=task_id,
                sha256=str(row[2]).strip(),
                size_bytes=int(row[3]),
                privacy_label=row[4],
            ),
            limits=ResearchLimits(
                max_sources=row[5],
                max_source_bytes=row[6],
                max_total_bytes=row[7],
                max_redirects=row[8],
                deadline_seconds=float(row[9]),
            ),
        )
        if canonical_sha256(request.model_dump(mode="json")) != str(row[10]).strip():
            raise KernelDenied("research_request_unconfirmed")
        if not 0 < request.question.size_bytes <= 65536:
            raise KernelDenied("brief_question_limit")
        artifact = uow.execute(
            "SELECT store_key,sha256,size_bytes,privacy_class FROM panestria.artifact WHERE id=%s AND task_id=%s",
            (request.question.artifact_id, task_id),
        ).fetchone()
        if artifact is None or tuple(str(v).strip() for v in artifact) != (
            request.question.sha256,
            request.question.sha256,
            str(request.question.size_bytes),
            request.question.privacy_label,
        ):
            raise KernelDenied("research_question_unconfirmed")
        with ResearchBlobStore(self.root, self.actor) as blobs:
            question = blobs.read(request.question.sha256, expected_size=request.question.size_bytes).decode("utf-8")
        rows = uow.execute(
            "SELECT id::text,report_sha256 FROM panestria.research_claim "
            "WHERE request_id=%s AND task_id=%s AND owner_id=%s AND project_id=%s ORDER BY seq LIMIT 65",
            (request_id, task_id, self.actor.owner_id, self.actor.project_id),
        ).fetchall()
        if len(rows) > 64:
            raise KernelDenied("brief_claim_limit")
        store = ClaimStore(self.root, self.actor)
        labels = [request.question.privacy_label]
        claims = []
        for claim_id, historical_sha in rows:
            try:
                checked = store.verify(uow, claim_id, request_id=request_id, task_id=task_id)
                citations = []
                for check in checked.report.checks:
                    if check.verdict != "EVIDENCE_PRESENT":
                        continue
                    passage = store.sources.resolve(uow, check.reference, task_id=task_id)
                    if len(passage.text.get_secret_value().encode()) > 8192:
                        raise KernelDenied("brief_passage_limit")
                    source = SourceRecordService().read(
                        uow, self.actor, check.reference.snapshot_id, request_id=request_id, task_id=task_id
                    )
                    if source.body_sha256 != check.source_metadata_sha256:
                        raise KernelDenied("brief_source_changed")
                    terminal = source.evidence.snapshot.terminal_url
                    assert terminal is not None and check.source_metadata_sha256 is not None
                    citations.append(
                        BriefCitation(
                            reference=check.reference,
                            source_metadata_sha256=check.source_metadata_sha256,
                            url=SecretStr(terminal),
                            quote=passage.text,
                            quote_was_supplied=check.quote_checked,
                            limitations=passage.limitations,
                        )
                    )
                labels.append(checked.privacy_label)
                claims.append(
                    BriefClaim(
                        claim_id=claim_id,
                        text=checked.payload.draft.claim.text,
                        kind=checked.payload.draft.claim.kind,
                        evidence_verdict=checked.report.verdict,
                        historical_report_sha256=checked.historical_report_sha256,
                        current_report_sha256=checked.current_report_sha256,
                        citations=tuple(citations),
                        diagnostics=tuple(
                            dict.fromkeys(
                                "quote_mismatch" if check.diagnostic == "quote_mismatch" else "source_unavailable"
                                for check in checked.report.checks
                                if check.verdict == "INVALID_EVIDENCE"
                            )
                        ),
                    )
                )
            except KernelDenied:
                # A historical PASS cannot hide current loss/corruption. No unchecked URL/text is displayed.
                labels.append("RESTRICTED")
                claims.append(
                    BriefClaim(
                        claim_id=claim_id,
                        evidence_verdict="UNAVAILABLE",
                        historical_report_sha256=str(historical_sha).strip(),
                        diagnostics=("claim_unavailable",),
                    )
                )
        label = derive_classification(labels).effective
        assert label is not None
        cursor = uow.execute(
            "SELECT coalesce(max(seq),0) FROM panestria.task_event WHERE goal_id=%s AND task_id=%s",
            (scope.goal_id, task_id),
        ).fetchone()
        assert cursor is not None
        brief = EvidenceBrief(
            scope=scope,
            request_id=request_id,
            request_sha256=str(row[10]).strip(),
            question=SecretStr(question),
            question_sha256=request.question.sha256,
            observed_at=datetime.now(UTC),
            event_cursor=int(cursor[0]),
            task_state=row[11],
            goal_status=row[12],
            privacy_label=label,
            claims=tuple(claims),
            collection=_collection(uow, task_id, request_id),
        )
        brief_json(brief)  # Enforce one aggregate output bound, including explicitly unwrapped protected text.
        return brief


def _collection(uow: UnitOfWork, task_id: str, request_id: str) -> CollectionObservation | None:
    # Historical dispatch/receipt observation; never runtime or semantic authority.
    prepared = uow.execute(
        "SELECT EXISTS(SELECT 1 FROM panestria.search_plan WHERE task_id=%s AND request_id=%s) "
        "OR EXISTS(SELECT 1 FROM panestria.fetch_plan WHERE task_id=%s AND request_id=%s)",
        (task_id, request_id, task_id, request_id),
    ).fetchone()
    if prepared is None or not prepared[0]:
        return None
    searches = uow.execute(
        "SELECT d.id::text,coalesce(o.status,'UNKNOWN'),o.candidate_count "
        "FROM panestria.search_dispatch d LEFT JOIN panestria.search_outcome o ON o.dispatch_id=d.id "
        "WHERE d.task_id=%s AND d.request_id=%s ORDER BY d.ordinal LIMIT 17",
        (task_id, request_id),
    ).fetchall()
    fetches = uow.execute(
        "SELECT d.id::text,coalesce(o.status,'UNKNOWN'),coalesce(o.diagnostic,'unconfirmed'),"
        "o.snapshot_id::text,d.reserved_body_bytes FROM panestria.fetch_dispatch d "
        "LEFT JOIN panestria.fetch_outcome o ON o.dispatch_id=d.id WHERE d.task_id=%s AND d.request_id=%s "
        "ORDER BY d.ordinal LIMIT 17",
        (task_id, request_id),
    ).fetchall()
    stopped = uow.execute(
        "SELECT payload->>'reason' FROM panestria.task_event WHERE task_id=%s "
        "AND kind='research.collection.stopped' AND payload->>'request_id'=%s ORDER BY seq DESC LIMIT 1",
        (task_id, request_id),
    ).fetchone()
    attempt = uow.execute(
        "SELECT status,lease_expires_at>clock_timestamp() FROM panestria.task_attempt "
        "WHERE task_id=%s ORDER BY attempt_number DESC LIMIT 1",
        (task_id,),
    ).fetchone()
    return CollectionObservation(
        searches=tuple(SearchObservation(dispatch_id=r[0], status=r[1], candidate_count=r[2]) for r in searches),
        fetches=tuple(
            FetchObservation(dispatch_id=r[0], status=r[1], diagnostic=r[2], snapshot_id=r[3], reserved_body_bytes=r[4])
            for r in fetches
        ),
        stop_reason=stopped[0] if stopped else None,
        latest_attempt_status=attempt[0] if attempt else None,
        lease_unexpired=bool(attempt and attempt[1]),
    )


def brief_json(brief: EvidenceBrief) -> bytes:
    """Explicit owner export only. Ordinary model/repr serialization keeps secrets masked."""
    body = brief.model_dump(mode="json")
    body["question"] = brief.question.get_secret_value()
    for item, claim in zip(body["claims"], brief.claims, strict=True):
        item["text"] = claim.text.get_secret_value() if claim.text is not None else None
        for citation_body, citation in zip(item["citations"], claim.citations, strict=True):
            citation_body["url"] = citation.url.get_secret_value()
            citation_body["quote"] = citation.quote.get_secret_value()
    raw = json.dumps(body, sort_keys=True, ensure_ascii=False, indent=2).encode()
    if len(raw) > MAX_BRIEF_BYTES:
        raise KernelDenied("brief_output_limit")
    return raw


def brief_html(brief: EvidenceBrief) -> bytes:
    # No script, remote resources, active links, raw HTML, markdown evaluation or site instructions.
    parts = [
        '<!doctype html><html lang="en"><meta charset="utf-8">',
        '<meta http-equiv="Content-Security-Policy" '
        "content=\"default-src 'none'; base-uri 'none'; form-action 'none'\">",
        '<meta name="referrer" content="no-referrer"><title>Retained research evidence</title><body>',
        "<h1>Retained research evidence</h1><p>Semantic support: NOT_ASSESSED. Contradictions: NOT_ASSESSED.</p>",
        f"<p>Classification: {brief.privacy_label}. Task: {escape(brief.task_state)}; "
        f"goal: {escape(brief.goal_status)}. This export grants no task completion.</p>",
        "<h2>Question (untrusted data)</h2><pre>" + escape(brief.question.get_secret_value()) + "</pre>",
        f"<p>Request: {brief.request_id}; event cursor: {brief.event_cursor}; "
        f"observed: {brief.observed_at.isoformat()}; request SHA256: {brief.request_sha256}</p>",
        "<h2>Limitations</h2><ul>",
        *(f"<li>{escape(value)}</li>" for value in brief.limitations),
        "</ul>",
    ]
    if brief.collection is not None:
        observed = brief.collection
        parts.extend(
            [
                "<h2>Collection observations</h2>",
                f"<p>Stop: {observed.stop_reason or 'no confirmed stop'}; "
                f"attempt: {observed.latest_attempt_status or 'none'}; "
                f"lease unexpired: {observed.lease_unexpired}.</p>",
                "<p>Dispatch and reserved body capacity are not measured upstream usage, cash or quota.</p><ul>",
                *(
                    f"<li>Search {s.dispatch_id}: {s.status}; candidates: {s.candidate_count}.</li>"
                    for s in observed.searches
                ),
                *(
                    f"<li>Fetch {f.dispatch_id}: {f.status}; {f.diagnostic}; "
                    f"reserved body bytes: {f.reserved_body_bytes}; "
                    f"snapshot: {f.snapshot_id or 'none'}.</li>"
                    for f in observed.fetches
                ),
                "</ul>",
            ]
        )
    parts.append("<h2>Draft statements</h2>")
    if not brief.claims:
        parts.append("<p>No retained claims. This is not a completed research brief.</p>")
    for claim in brief.claims:
        parts.extend(
            [
                f"<article><h3>{claim.claim_id}</h3><p>Evidence: {claim.evidence_verdict}; support: NOT_ASSESSED.</p>",
                "<pre>"
                + escape(claim.text.get_secret_value() if claim.text is not None else "[unavailable]")
                + "</pre>",
                "<p>Diagnostics: " + escape(", ".join(claim.diagnostics) or "none") + "</p>",
                f"<p>Historical report: {claim.historical_report_sha256}; "
                f"current report: {claim.current_report_sha256 or 'unavailable'}</p>",
            ]
        )
        for citation in claim.citations:
            ref = citation.reference
            parts.extend(
                [
                    "<section><h4>Retained passage (untrusted source text)</h4><p>Source URL (display only): "
                    + escape(citation.url.get_secret_value())
                    + "</p>",
                    "<blockquote><pre>" + escape(citation.quote.get_secret_value()) + "</pre></blockquote>",
                    f"<p>Snapshot: {ref.snapshot_id}; UTF-8 bytes [{ref.start}, {ref.end}); "
                    f"text SHA256: {ref.text_sha256}; metadata SHA256: {citation.source_metadata_sha256}; "
                    f"original quote supplied: {citation.quote_was_supplied}.</p>",
                    "<p>Source limitations: "
                    + escape(", ".join(citation.limitations) or "none recorded")
                    + "</p></section>",
                ]
            )
        parts.append("</article>")
    parts.append("</body></html>")
    raw = "\n".join(parts).encode()
    if len(raw) > MAX_BRIEF_BYTES:
        raise KernelDenied("brief_output_limit")
    return raw
