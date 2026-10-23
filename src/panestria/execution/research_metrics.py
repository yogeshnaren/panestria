"""Explicit retained-draft measurements; no inference, search, judgments or task writes."""

import fcntl
import hashlib
import json
import math
import os
import stat
from collections import Counter
from datetime import UTC, datetime
from itertools import islice
from pathlib import Path
from typing import Any
from uuid import UUID

from panestria.config_local import read_private
from panestria.execution.research_brief import _collection
from panestria.execution.research_review import RECORDED, OwnerResearchReview
from panestria.execution.research_synthesis import RETURNED, STARTED
from panestria.kernel.uow import UnitOfWork
from panestria.telemetry.ask_metrics import _private
from panestria.telemetry.performance import (
    CATALOG,
    LIMIT,
    Measurement,
    MissingReason,
    PerformanceSnapshot,
    save_snapshot,
)


def capture_research_metrics(service: OwnerResearchReview, request_id: str, directory: Path) -> dict[str, str]:
    """Reuse protected current-draft/review validation in one canonical snapshot.

    Existing inspection takes project/task locks; this reader writes no DB rows
    and performs no runtime/model/certificate or credential initialization.
    """
    if str(UUID(request_id)) != request_id:
        raise ValueError("invalid_research_request")
    observed = datetime.now(UTC)
    with service.connect() as c:
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        draft = service._inspect(c, request_id)
        task = draft.packet.scope.task_id
        timing = c.execute(
            "SELECT kind,seq,occurred_at FROM panestria.task_event WHERE task_id=%s "
            "AND kind IN (%s,%s) AND payload->>'request_id'=%s "
            "AND payload->>'synthesis_id'=%s ORDER BY seq LIMIT 3",
            (task, STARTED, RETURNED, request_id, draft.synthesis_id),
        ).fetchall()
        if len(timing) != 2 or [row[0] for row in timing] != [STARTED, RETURNED]:
            raise ValueError("research_metrics_timing_unconfirmed")
        elapsed = (timing[1][2] - timing[0][2]).total_seconds()
        if not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError("research_metrics_timing_invalid")
        collection = _collection(UnitOfWork(c), task, request_id)
        row = c.execute(
            "SELECT seq,payload FROM panestria.task_event WHERE task_id=%s AND kind=%s "
            "AND payload->>'request_id'=%s ORDER BY seq DESC LIMIT 1",
            (task, RECORDED, request_id),
        ).fetchone()
        judgments = Counter[str]()
        if row is not None:
            review = service._read_review(c, request_id, row[1])
            judgments.update(claim.verdict for claim in review.claims)
        # Allowlist only numeric metadata/opaque IDs. Do not serialize the draft,
        # question, passages, URLs, rationale, prompt or their private content hashes.
        source: dict[str, Any] = {
            "schema_version": 1,
            "kind": "derived-research-runtime-metrics",
            "authority": "DERIVED_MEASUREMENTS_ONLY",
            "owner_id": service.actor.owner_id,
            "project_id": service.actor.project_id,
            "request_id": request_id,
            "task_id": task,
            "synthesis_id": draft.synthesis_id,
            "model_ref": draft.model_ref,
            "model_digest": draft.model_digest,
            "model_manifest_sha256": draft.model_manifest.sha256() if draft.model_manifest else None,
            "input_tokens": draft.input_tokens,
            "output_tokens": draft.output_tokens,
            "claim_count": len(draft.response.claims),
            "selected_passages": len(draft.packet.passages),
            "omitted_passages": draft.packet.omitted_passages,
            "started_event_seq": timing[0][1],
            "returned_event_seq": timing[1][1],
            "started_at": timing[0][2].astimezone(UTC).isoformat(),
            "returned_at": timing[1][2].astimezone(UTC).isoformat(),
            "intent_to_return_seconds": elapsed,
            "search_receipts": dict(Counter(s.status for s in collection.searches)) if collection else None,
            "fetch_receipts": dict(Counter(f.status for f in collection.fetches)) if collection else None,
            "reserved_body_bytes": sum(f.reserved_body_bytes for f in collection.fetches) if collection else None,
            "owner_review_event_seq": row[0] if row else None,
            "owner_judgments": dict(judgments) if row else None,
            "assessment_source": "OWNER_REPORTED" if row else "NOT_ASSESSED",
            "qualification": "NOT_ASSESSED",
            "semantic_accuracy": "NOT_MEASURED",
        }
    raw = json.dumps(source, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(raw).hexdigest()
    observations = []

    def add(
        metric: str,
        value: float | int | None,
        samples: int,
        *,
        scope: str = "runtime_research",
        reason: MissingReason = "UNMEASURED",
    ) -> None:
        observations.append(
            Measurement(
                metric=metric,
                value=float(value) if value is not None else None,
                unit=CATALOG[metric],
                samples=samples,
                scope=scope,
                model=draft.model_ref,
                model_digest=draft.model_digest,
                evidence="sources/" + digest,
                evidence_sha256=digest,
                reason=reason if value is None else None,
            )
        )

    add("latency.research_synthesis_lifecycle", elapsed, 1)
    add("usage.research_input_tokens", draft.input_tokens, 1)
    add("usage.research_output_tokens", draft.output_tokens, 1)
    add("research.reserved_body_bytes", source["reserved_body_bytes"], len(collection.fetches) if collection else 0)
    for records, success, metric in (
        (source["search_receipts"], "RETURNED", "research.search_returned_receipt_fraction"),
        (source["fetch_receipts"], "RETAINED", "research.fetch_retained_receipt_fraction"),
    ):
        count = sum(records.values()) if records else 0
        add(
            metric,
            records.get(success, 0) / count if count else None,
            count,
            reason="UNMEASURED" if records is None else "UNDEFINED_DENOMINATOR",
        )
    assessed = sum(v for k, v in judgments.items() if k != "NOT_FACTUAL")
    for verdict, metric in (
        ("SUPPORTED", "review.owner_supported_fraction"),
        ("CONTRADICTED", "review.owner_contradicted_fraction"),
    ):
        add(
            metric,
            judgments[verdict] / assessed if assessed else None,
            assessed,
            scope="runtime_research_owner_review",
            reason="UNMEASURED" if row is None else "UNDEFINED_DENOMINATOR",
        )
    add("quality.correct_fraction", None, 0)
    add("cost.actual", None, 0)
    snapshot = PerformanceSnapshot(
        captured_at=observed,
        observations=tuple(observations),
        missing_areas=(
            "semantic_accuracy",
            "automatic_factual_support",
            "retrieval_recall",
            "model_only_latency",
            "actual_cash",
            "resource_samples",
            "latency_distribution",
            "runtime_build_source",
            "release_qualification",
        ),
    )
    return _save(directory, raw, digest, snapshot)


def _save(directory: Path, raw: bytes, digest: str, snapshot: PerformanceSnapshot) -> dict[str, str]:
    if len(raw) > 16 * 1024:
        raise ValueError("research_metrics_source_limit")
    _private(directory)
    sources = directory / "sources"
    _private(sources)
    fd = os.open(directory / "capture.lock", os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("metrics_lock_must_be_private")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        files = list(islice(directory.iterdir(), 4097)) + list(islice(sources.iterdir(), 4097))
        if len(files) > 4096 or sum(p.lstat().st_size for p in files) + len(raw) + LIMIT > 16 * 1024 * 1024:
            raise ValueError("research_metrics_history_budget_reached")
        path = sources / digest
        try:
            target = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            if read_private(path, 16 * 1024) != raw:
                raise ValueError("research_metrics_source_mismatch") from None
        else:
            with os.fdopen(target, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        saved = save_snapshot(directory, snapshot)
    finally:
        os.close(fd)
    return {
        "status": "SAVED",
        "snapshot": saved.name,
        "source_sha256": digest,
        "authority": "DERIVED_MEASUREMENTS_ONLY",
    }
