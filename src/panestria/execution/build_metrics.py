"""Opt-in derived Build measurements. Never task, approval or qualification authority."""

import json
import math
import os
import re
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg

from panestria.contracts.invocation import InvocationBinding
from panestria.execution.proposal_demo import _lock, _private
from panestria.kernel.build import BuildEvidenceService, BuildEvidenceStore
from panestria.kernel.build_progress import BuildProgressService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork
from panestria.telemetry.performance import CATALOG, LIMIT, Measurement, PerformanceSnapshot, save_snapshot


def capture_build_metrics(
    connect: Callable[[], psycopg.Connection[Any]], actor: Actor, store: BuildEvidenceStore, directory: Path, goal: str
) -> dict[str, Any]:
    records = []
    timings: dict[str, list[float]] = defaultdict(list)
    with connect() as c:
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        progress = BuildProgressService().inspect(UnitOfWork(c), actor, goal, BuildEvidenceService(store))
        rows = c.execute(
            "SELECT i.id::text,i.task_id::text,i.attempt_id::text,i.binding,i.binding_sha256,"
            "i.state,i.receipt_sha256,i.created_at,i.finished_at FROM panestria.worker_invocation i "
            "JOIN panestria.task t ON t.id=i.task_id WHERE t.goal_id=%s ORDER BY i.created_at,i.id LIMIT 65",
            (goal,),
        ).fetchall()
        if len(rows) > 64:
            raise ValueError("runtime_metrics_invocation_limit")
        for identity, task, attempt, document, binding_hash, state, receipt, created, finished in rows:
            binding = InvocationBinding.model_validate_json(json.dumps(document))
            scope = binding.scope
            if (
                binding.sha256() != str(binding_hash).strip()
                or (str(scope.owner_id), str(scope.project_id), str(scope.task_id), str(scope.attempt_id))
                != (actor.owner_id, actor.project_id, task, attempt)
                or scope.contract_sha256 != progress.contract_sha256
            ):
                raise ValueError("runtime_metrics_binding_mismatch")
            present, source, elapsed = False, None, None
            if receipt:
                try:
                    body = json.loads(store.read_blob(str(receipt).strip()))
                    present = True
                    versions = body.get("runtime_versions", {}) if isinstance(body, dict) else {}
                    candidate = versions.get("source_sha256") if isinstance(versions, dict) else None
                    if isinstance(candidate, str) and re.fullmatch(r"[a-f0-9]{64}", candidate):
                        source = candidate
                except (ValueError, OSError, KernelDenied):
                    pass
            if state == "RETURNED" and present and finished is not None:
                elapsed = (finished - created).total_seconds()
                if not math.isfinite(elapsed) or elapsed < 0:
                    raise ValueError("runtime_metrics_invalid_duration")
                timings[binding.kind].append(elapsed)
            records.append(
                {
                    "invocation_id": identity,
                    "task_id": task,
                    "attempt_id": attempt,
                    "kind": binding.kind,
                    "binding_sha256": binding.sha256(),
                    "configuration_sha256": binding.configuration_sha256,
                    "state": state,
                    "receipt_sha256": str(receipt).strip() if receipt else None,
                    "receipt_present": present,
                    "created_at": created.astimezone(UTC).isoformat(),
                    "finished_at": finished.astimezone(UTC).isoformat() if finished else None,
                    "intent_to_return_seconds": elapsed,
                    "native_controller_source_sha256": source,
                }
            )
    # No prompts, source code, credentials or model answers are copied. Excluding
    # capture time/event cursor makes repeated unchanged observations deduplicate.
    raw = json.dumps(
        {
            "schema_version": 1,
            "kind": "derived-build-runtime-metrics",
            "owner_id": actor.owner_id,
            "project_id": actor.project_id,
            "goal_id": goal,
            "contract_sha256": progress.contract_sha256,
            "final_evidence_sha256": progress.final_evidence_sha256,
            "records": records,
            "qualification": "NOT_ASSESSED",
            "authority": "DERIVED_MEASUREMENTS_ONLY",
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    if len(raw) > 32 * 1024:
        raise ValueError("runtime_metrics_source_limit")
    directory = _private(directory)
    sources = BuildEvidenceStore(_private(directory / "sources"))
    lock = directory / "capture.lock"
    fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    os.close(fd)
    with _lock(lock):
        files, source_files = list(directory.iterdir()), list(sources.root.iterdir())
        if sum(p.suffix == ".json" for p in files) >= 4096 or len(source_files) >= 4096:
            raise ValueError("runtime_metrics_history_count_limit")
        # Reserve the maximum snapshot before retaining a new source, so normal
        # runtime captures cannot grow raw CAS after the history budget is full.
        used = sum(p.lstat().st_size for p in files + source_files)
        if used + len(raw) + LIMIT > 16 * 1024 * 1024:
            raise ValueError("runtime_metrics_history_budget_reached")
        digest = sources.write_report(raw)
        observations = []

        def add(metric: str, value: float | None, samples: int, scope: str) -> None:
            observations.append(
                Measurement(
                    metric=metric,
                    value=value,
                    unit=CATALOG[metric],
                    samples=samples,
                    scope=scope,
                    evidence="sources/" + digest,
                    evidence_sha256=digest,
                    reason="UNMEASURED" if value is None else None,
                )
            )

        for kind in sorted({r["kind"] for r in records}):
            values = sorted(timings[kind])
            for quantile, label in ((0.5, "p50"), (0.95, "p95")):
                value = values[math.ceil(quantile * len(values)) - 1] if values else None
                add("latency.invocation_lifecycle_" + label, value, len(values), "runtime_" + kind)
        add(
            "runtime.receipt_present_fraction",
            sum(r["receipt_present"] for r in records) / len(records) if records else None,
            len(records),
            "runtime_build",
        )
        total = progress.required_checks_total
        confirmed = progress.final_evidence_sha256 is not None and not any(
            r.required and r.verdict in {"NOT_RUN", "UNCONFIRMED"} for r in progress.requirements
        )
        add(
            "verification.required_pass_fraction",
            progress.required_checks_passed / total if confirmed and total else None,
            total if confirmed else 0,
            "runtime_build",
        )
        add("quality.correct_fraction", None, 0, "runtime_build")
        add("cost.actual", None, 0, "runtime_build")
        snapshot = PerformanceSnapshot(
            captured_at=datetime.fromisoformat(progress.observed_at),
            observations=tuple(observations),
            missing_areas=(
                "semantic_accuracy",
                "actual_cash",
                "model_only_latency",
                "resource_samples",
                "cross_mode_aggregation",
                "release_qualification",
            ),
        )
        path = save_snapshot(directory, snapshot)
    return {"status": "SAVED", "snapshot": path.name, "source_sha256": digest, "authority": "DERIVED_MEASUREMENTS_ONLY"}
