"""Private, append-only derived measurements. Never task state or release authority."""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Self
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, FiniteFloat, StrictInt, model_validator

from panestria.config_local import read_private

CATALOG = {
    "latency.invocation_lifecycle_p50": "seconds",
    "latency.invocation_lifecycle_p95": "seconds",
    "runtime.receipt_present_fraction": "fraction",
    "verification.required_pass_fraction": "fraction",
    "quality.correct_fraction": "fraction",
    "quality.answered_accuracy": "fraction",
    "quality.supported_precision": "fraction",
    "quality.coverage": "fraction",
    "quality.false_supported": "count",
    "latency.case_p50": "seconds",
    "latency.case_p95": "seconds",
    "latency.ask_warm_p95": "seconds",
    "resource.model_vram": "bytes",
    "cost.actual": "USD",
    "ci.workflow_wall": "seconds",
    "testing.mutation_detection": "fraction",
    "testing.survivors": "count",
}
LIMIT = 256 * 1024
MissingReason = Literal["UNMEASURED", "NO_BASELINE", "INCOMPLETE_RUN", "UNDEFINED_DENOMINATOR"]


class Closed(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)


class Measurement(Closed):
    metric: str
    value: FiniteFloat | None
    unit: str
    samples: StrictInt = Field(ge=0)
    scope: str = Field(pattern=r"^[a-z0-9_-]{1,96}$")
    model: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9._:-]{1,128}$")
    model_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    corpus_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    rubric_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    fold: Literal["calibration", "qualification"] | None = None
    source_commit: str | None = Field(default=None, pattern=r"^[a-f0-9]{40}$")
    source_dirty: bool | None = None
    evidence: str = Field(pattern=r"^[a-zA-Z0-9_./-]{1,160}$")
    evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: MissingReason | None = None

    @model_validator(mode="after")
    def honest_value(self) -> Self:
        if CATALOG.get(self.metric) != self.unit:
            raise ValueError("metric_or_unit_unknown")
        if (self.value is None) != (self.reason is not None):
            raise ValueError("missing_value_requires_reason")
        if self.value is not None and (self.value < 0 or (self.unit == "fraction" and self.value > 1)):
            raise ValueError("metric_out_of_range")
        return self


class PerformanceSnapshot(Closed):
    schema_version: StrictInt = Field(default=1, ge=1, le=1)
    captured_at: AwareDatetime
    authority: Literal["DERIVED_MEASUREMENTS_ONLY"] = "DERIVED_MEASUREMENTS_ONLY"
    observations: tuple[Measurement, ...] = Field(max_length=128)
    missing_areas: tuple[str, ...]


def _read(path: Path) -> tuple[Any, str]:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 2 * 1024 * 1024:
            raise ValueError("report_size_or_type_invalid")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(2 * 1024 * 1024 + 1)
        if len(raw) != info.st_size:
            raise ValueError("report_changed")
        return json.loads(raw), hashlib.sha256(raw).hexdigest()
    finally:
        os.close(fd)


def collect_performance(
    evidence_root: Path, *, mutation_reports: tuple[Path, ...] = (), ci_report: Path | None = None
) -> PerformanceSnapshot:
    """Read only named supported formats; never infer accuracy from test counts."""
    if not evidence_root.is_dir() or len(mutation_reports) > 8:
        raise ValueError("invalid_evidence_selection")
    measurements: list[Measurement] = []

    def add(
        metric: str, value: Any, samples: int, context: dict[str, Any], reason: MissingReason = "UNMEASURED"
    ) -> None:
        measurements.append(
            Measurement(
                metric=metric,
                value=value,
                samples=samples,
                unit=CATALOG[metric],
                reason=reason if value is None else None,
                **context,
            )
        )

    cohorts = [
        (lane, path.parent)
        for lane in ("local", "native")
        for path in sorted(evidence_root.glob(f"{lane}-entailment-*/report.json"))
    ]
    if len(cohorts) > 8:
        raise ValueError("select_a_smaller_evidence_root")
    for lane, directory in cohorts:
        name = directory.name
        report, _ = _read(directory / "report.json")
        folds, digest = _read(directory / "actual-observations.json")
        if (
            report["artifacts"]["actual-observations.json"] != digest
            or len(folds) != 2
            or {fold["fold"] for fold in folds} != {"calibration", "qualification"}
        ):
            raise ValueError("observation_hash_or_fold_mismatch")
        for fold in folds:
            if fold["status"] != "COMPLETE":
                continue
            score = fold["score"]
            count = score["total"]
            context = {
                "scope": f"historical_{lane}_snli",
                "model": fold.get("model_ref", fold.get("model")),
                "model_digest": fold.get("model_digest"),
                "corpus_sha256": fold["corpus_sha256"],
                "rubric_sha256": fold["rubric_sha256"],
                "fold": fold["fold"],
                "source_commit": report["source_commit"],
                "evidence": f"{name}/actual-observations.json",
                "evidence_sha256": digest,
            }
            for metric, key in (
                ("quality.correct_fraction", "correct_fraction"),
                ("quality.answered_accuracy", "accuracy_on_answered"),
                ("quality.supported_precision", "supported_precision"),
                ("quality.coverage", "coverage"),
                ("quality.false_supported", "false_supported_count"),
            ):
                denominator = (
                    score["answered"]
                    if metric == "quality.answered_accuracy"
                    else score["supported_predictions"]
                    if metric == "quality.supported_precision"
                    else count
                )
                add(metric, score[key], denominator, context, "UNDEFINED_DENOMINATOR")
            times = sorted(case["elapsed_seconds"] for case in fold.get("cases", []))
            if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in times):
                raise ValueError("invalid_latency_sample")
            for quantile, metric in ((0.5, "latency.case_p50"), (0.95, "latency.case_p95")):
                value = times[math.ceil(quantile * len(times)) - 1] if times and len(times) == count else None
                add(metric, value, len(times), context)
            cash = fold.get("cash_actual_microusd")
            add("cost.actual", cash / 1_000_000 if cash is not None else None, 0, context)

    gpu_path = evidence_root / "r1-gpu-startup-2026-10-18/report.json"
    if gpu_path.exists():
        gpu, digest = _read(gpu_path)
        source = next(r["candidate_commit"] for r in gpu["reports"] if r["path"] == "baseline-offline-failed.xml")
        context = {
            "scope": "historical_failed_gpu_prerequisite",
            "source_commit": source,
            "evidence": "r1-gpu-startup-2026-10-18/report.json",
            "evidence_sha256": digest,
        }
        add("latency.ask_warm_p95", gpu["observations"]["warm_ask_p95_seconds"], 0, context)
        add("resource.model_vram", gpu["observations"]["observed_model_size_vram_bytes"], 1, context)

    for path in mutation_reports:
        report, digest = _read(path)
        if report.get("kind") != "mutation_pilot" or report.get("authority") != "TEST_EFFECTIVENESS_ONLY":
            raise ValueError("unsupported_mutation_report")
        mutants = report["mutants"]
        detected = sum(item["status"] == "DETECTED" for item in mutants)
        survived = sum(item["status"] == "SURVIVED" for item in mutants)
        complete = detected + survived == len(mutants) > 0 and report["exit_code"] == 0
        baseline = report.get("baseline_passed", False)
        context = {
            "scope": "mutation_five_function_pilot",
            "source_commit": report["source_commit"],
            "source_dirty": report["dirty"],
            "evidence": "mutation-report",
            "evidence_sha256": digest,
        }
        add(
            "testing.mutation_detection",
            detected / len(mutants) if complete and baseline else None,
            len(mutants),
            context,
            "INCOMPLETE_RUN" if baseline else "NO_BASELINE",
        )
        add("testing.survivors", survived, len(mutants), context)

    if ci_report is not None:
        report, digest = _read(ci_report)
        for name, key in (("baseline", "main_commit"), ("main_followup", "commit")):
            item = report[name]
            context = {
                "scope": f"historical_ci_{name}",
                "source_commit": item[key],
                "evidence": "ci-audit-report",
                "evidence_sha256": digest,
            }
            add("ci.workflow_wall", item["workflow_wall_seconds"], 1, context)

    return PerformanceSnapshot(
        captured_at=datetime.now(UTC),
        observations=tuple(measurements),
        missing_areas=(
            "current_candidate_end_to_end",
            "ask_answer_and_retrieval_quality",
            "research_domain_quality",
            "build_success_and_false_done_rate",
            "crash_recovery_success_rate",
            "current_cpu_ram_disk_growth",
            "current_quota_and_actual_cost",
        ),
    )


def save_snapshot(directory: Path, snapshot: PerformanceSnapshot) -> Path:
    """New private immutable file each capture; no pruning or overwriting history."""
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("metrics_directory_must_be_private")
    # Refuse growth at a small explicit budget. The owner chooses retention.
    data = snapshot.model_dump_json(indent=2).encode() + b"\n"
    if len(data) > LIMIT:
        raise ValueError("metrics_snapshot_too_large")
    if sum(p.lstat().st_size for p in directory.iterdir()) + len(data) > 16 * 1024 * 1024:
        raise ValueError("metrics_history_budget_reached")
    path = directory / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}-{uuid4().hex}.json"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return path


def latest_snapshot(directory: Path) -> PerformanceSnapshot:
    paths = list(directory.glob("*.json"))
    if not 0 < len(paths) <= 4096:
        raise ValueError("metrics_history_empty_or_too_large")
    snapshots = [PerformanceSnapshot.model_validate_json(read_private(path, LIMIT)) for path in paths]
    return max(snapshots, key=lambda item: item.captured_at)
