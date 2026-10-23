"""Read retained runtime measurements without averaging unlike cohorts or recaptures."""

import hashlib
import json
import os
import re
import stat
from datetime import UTC, datetime
from itertools import islice
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import AwareDatetime, Field

from panestria.config_local import read_private
from panestria.telemetry.performance import LIMIT, Closed, Measurement, PerformanceSnapshot

BUDGET = 16 * 1024 * 1024
Mode = Literal["ASK", "BUILD", "DELEGATE"]
KINDS: dict[str, Mode] = {
    "derived-ask-runtime-metrics": "ASK",
    "derived-build-runtime-metrics": "BUILD",
    "derived-research-runtime-metrics": "DELEGATE",
}


class OverviewEntry(Closed):
    owner_id: UUID
    project_id: UUID
    mode: Mode
    latest_capture_at: AwareDatetime
    capture_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    # Inventory only: this count is never a sample denominator or accuracy score.
    distinct_records: int = Field(ge=1, le=4096)
    measurement: Measurement


class PerformanceOverview(Closed):
    schema_version: Literal[1] = 1
    authority: Literal["DERIVED_MEASUREMENTS_ONLY"] = "DERIVED_MEASUREMENTS_ONLY"
    created_at: AwareDatetime
    interpretation: Literal["LATEST_CAPTURE_PER_COHORT_NOT_A_POOLED_BENCHMARK"] = (
        "LATEST_CAPTURE_PER_COHORT_NOT_A_POOLED_BENCHMARK"
    )
    histories: int = Field(ge=1, le=8)
    snapshots_read: int = Field(ge=1, le=4096)
    historical_observations_omitted: int = Field(ge=0)
    entries: tuple[OverviewEntry, ...] = Field(max_length=128)
    missing_areas: tuple[str, ...] = Field(max_length=128)


def _directory(path: Path) -> None:
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError("metrics_path_invalid")
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("metrics_directory_must_be_private")


def runtime_overview(directories: tuple[Path, ...]) -> PerformanceOverview:
    """Validate saved snapshots and runtime source hashes; no DB, HTTP or model access.

    Capture time selects the latest observation. It does not renew the original
    measurement, policy, consent, model qualification or accuracy assessment.
    """
    if not 1 <= len(directories) <= 8 or len(set(directories)) != len(directories):
        raise ValueError("metrics_history_selection_invalid")
    selected: list[tuple[Path, Path]] = []
    for directory in directories:
        _directory(directory)
        selected.extend((directory, p) for p in islice(directory.glob("*.json"), 4097))
    if not 1 <= len(selected) <= 4096 or sum(p.lstat().st_size for _, p in selected) > BUDGET:
        raise ValueError("metrics_history_empty_or_too_large")
    # Key includes scope, owner/project, model and evaluation/source identity.
    latest: dict[tuple[object, ...], tuple[datetime, str, Measurement, str, str, Mode]] = {}
    records: dict[tuple[object, ...], set[tuple[str, str]]] = {}
    missing: set[str] = {"pooled_latency_distribution", "release_qualification"}
    omitted = 0
    # Cache only validated bounded metadata. No source text is included in output.
    sources: dict[tuple[Path, str], tuple[str, str, str, str]] = {}
    read_bytes = sum(p.lstat().st_size for _, p in selected)
    for directory, path in selected:
        raw = read_private(path, LIMIT)
        capture = hashlib.sha256(raw).hexdigest()
        snapshot = PerformanceSnapshot.model_validate_json(raw)
        if any(re.fullmatch(r"[a-z][a-z0-9_]{0,95}", area) is None for area in snapshot.missing_areas):
            raise ValueError("metrics_missing_area_invalid")
        missing.update(snapshot.missing_areas)
        for observation in snapshot.observations:
            match = re.fullmatch(r"sources/([a-f0-9]{64})", observation.evidence)
            if match is None:
                omitted += 1  # Historical corpus/CI/mutation views keep their own existing command.
                continue
            digest = match[1]
            if digest != observation.evidence_sha256:
                raise ValueError("metrics_source_hash_mismatch")
            source_key = (directory, digest)
            if source_key not in sources:
                _directory(directory / "sources")
                body = read_private(directory / "sources" / digest, 64 * 1024)
                read_bytes += len(body)
                if read_bytes > BUDGET or hashlib.sha256(body).hexdigest() != digest:
                    raise ValueError("metrics_source_hash_or_budget_invalid")
                document = json.loads(body)
                kind = document["kind"]
                if (
                    type(document.get("schema_version")) is not int
                    or document["schema_version"] != 1
                    or kind not in KINDS
                    or document.get("authority") != "DERIVED_MEASUREMENTS_ONLY"
                ):
                    raise ValueError("metrics_source_kind_invalid")
                owner, project = str(UUID(document["owner_id"])), str(UUID(document["project_id"]))
                record = str(UUID(document["goal_id"] if KINDS[kind] == "BUILD" else document["request_id"]))
                sources[source_key] = (kind, owner, project, record)
            kind, owner, project, record = sources[source_key]
            mode = KINDS[kind]
            if not observation.scope.startswith("runtime_"):
                raise ValueError("metrics_runtime_scope_invalid")
            cohort = (
                owner,
                project,
                kind,
                observation.scope,
                observation.metric,
                observation.model,
                observation.model_digest,
                observation.source_commit,
                observation.source_dirty,
                observation.corpus_sha256,
                observation.rubric_sha256,
                observation.fold,
            )
            records.setdefault(cohort, set()).add((kind, record))
            candidate = (snapshot.captured_at, capture, observation, owner, project, mode)
            if cohort not in latest or candidate[:2] > latest[cohort][:2]:
                latest[cohort] = candidate
    if len(latest) > 128:
        raise ValueError("metrics_select_fewer_cohorts")
    entries = tuple(
        OverviewEntry(
            owner_id=UUID(value[3]),
            project_id=UUID(value[4]),
            mode=value[5],
            latest_capture_at=value[0],
            capture_sha256=value[1],
            distinct_records=len(records[key]),
            measurement=value[2],
        )
        for key, value in sorted(latest.items(), key=lambda item: repr(item[0]))
    )
    return PerformanceOverview(
        created_at=datetime.now(UTC),
        histories=len(directories),
        snapshots_read=len(selected),
        historical_observations_omitted=omitted,
        entries=entries,
        missing_areas=tuple(sorted(missing)),
    )


def save_overview(directory: Path, overview: PerformanceOverview) -> Path:
    """Append a private small derived report. Caller selects a separate output directory."""
    if not directory.is_absolute() or directory.resolve() != directory:
        raise ValueError("metrics_path_invalid")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    _directory(directory)
    raw = overview.model_dump_json(indent=2).encode() + b"\n"
    if len(raw) > LIMIT:
        raise ValueError("metrics_overview_too_large")
    # Exclusive nonblocking lock prevents two writers bypassing the history cap.
    import fcntl

    descriptor = os.open(directory / ".overview.lock", os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("metrics_lock_must_be_private")
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        files = list(islice(directory.iterdir(), 4097))
        if len(files) >= 4096 or sum(p.lstat().st_size for p in files) + len(raw) > BUDGET:
            raise ValueError("metrics_history_budget_reached")
        path = directory / f"overview-{uuid4().hex}.json"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        return path
    finally:
        os.close(descriptor)
