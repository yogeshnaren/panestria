"""Explicit metadata-only capture from an authenticated canonical Ask receipt."""

import fcntl
import hashlib
import json
import math
import os
import re
import stat
from datetime import UTC, datetime
from itertools import islice
from pathlib import Path
from typing import Any
from uuid import UUID

from panestria.config_local import read_private
from panestria.contracts.model_manifest import ModelManifest
from panestria.telemetry.performance import CATALOG, LIMIT, Measurement, PerformanceSnapshot, save_snapshot

_FIELDS = {
    "input_tokens": ("usage.ask_input_tokens", "count"),
    "output_tokens": ("usage.ask_output_tokens", "count"),
    "elapsed_seconds": ("latency.ask_generation", "seconds"),
    "first_token_seconds": ("latency.ask_first_token", "seconds"),
    "decode_tokens_per_second": ("runtime.ask_decode_tokens_per_second", "tokens/second"),
    "cash_actual_microusd": ("cost.actual", "USD"),
}
_STATES = {"PREPARED", "RUNNING", "COMPLETED", "CANCELLED", "FAILED", "UNAVAILABLE"}


def ask_observation(owner: str, project: str, request_id: str, receipt: dict[str, Any]) -> dict[str, Any]:
    """Validate and allowlist; never hash/copy a prompt, response or profile field."""
    if (
        receipt.get("request_id") != str(UUID(request_id))
        or receipt.get("state") not in _STATES
        or receipt.get("offline") is not True
        or receipt.get("response_retained") is not False
        or "text" in receipt
    ):
        raise ValueError("ask_receipt_unconfirmed")
    protected = "profile_context" in receipt
    if protected and (
        receipt.get("response_sha256") is not None
        or receipt.get("response_digest_mode") != "OMITTED_RESTRICTED_PROFILE"
    ):
        raise ValueError("ask_private_receipt_unconfirmed")
    usage = receipt.get("usage")
    if not isinstance(usage, dict):
        raise ValueError("ask_usage_unconfirmed")
    model = receipt.get("model_ref")
    if model is not None and (type(model) is not str or re.fullmatch(r"[a-zA-Z0-9._:-]{1,128}", model) is None):
        raise ValueError("ask_model_ref_invalid")
    values = {}
    complete = receipt["state"] == "COMPLETED"
    for name in _FIELDS:
        value = usage.get(name)
        if value is not None:
            count = name.endswith("tokens") or name == "cash_actual_microusd"
            if (
                type(value) not in (int, float)
                or (count and type(value) is not int)
                or not math.isfinite(value)
                or value < 0
            ):
                raise ValueError("ask_usage_invalid")
        values[name] = value if complete else None
    elapsed, first = values["elapsed_seconds"], values["first_token_seconds"]
    if elapsed is not None and first is not None and first > elapsed:
        raise ValueError("ask_latency_inconsistent")
    manifest = None
    if receipt.get("model_manifest") is not None:
        manifest = ModelManifest.model_validate_json(json.dumps(receipt["model_manifest"]))
        if manifest.model_ref != model or (complete and usage.get("model_manifest_sha256") != manifest.sha256()):
            raise ValueError("ask_model_manifest_mismatch")
    elif usage.get("model_manifest_sha256") is not None:
        raise ValueError("ask_model_manifest_missing")
    return {
        "schema_version": 1,
        "kind": "derived-ask-runtime-metrics",
        "authority": "DERIVED_MEASUREMENTS_ONLY",
        "owner_id": str(UUID(owner)),
        "project_id": str(UUID(project)),
        "request_id": str(UUID(request_id)),
        "context_pack_id": str(UUID(receipt["context_pack_id"])),
        "state": receipt["state"],
        "scope": "runtime_profile_ask" if protected else "runtime_local_ask",
        "model_ref": model,
        "context_model_manifest_sha256": manifest.sha256() if manifest else None,
        "weights_sha256": manifest.weights_sha256 if manifest else None,
        "finish_reason": usage.get("finish_reason") if usage.get("finish_reason") in ("stop", "length") else None,
        "measurements": values,
        "measurement_time": "NOT_IN_RECEIPT",
        "runtime_build_source": "NOT_IN_RECEIPT",
        "qualification": "NOT_ASSESSED",
    }


def _private(directory: Path) -> None:
    if not directory.is_absolute() or directory.resolve() != directory:
        raise ValueError("metrics_path_invalid")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("metrics_directory_must_be_private")


def capture_ask_metrics(
    directory: Path, owner: str, project: str, request_id: str, receipt: dict[str, Any]
) -> dict[str, str]:
    source = ask_observation(owner, project, request_id, receipt)
    raw = json.dumps(source, sort_keys=True, separators=(",", ":")).encode()
    if len(raw) > 16 * 1024:
        raise ValueError("ask_metrics_source_limit")
    digest = hashlib.sha256(raw).hexdigest()
    _private(directory)
    sources = directory / "sources"
    _private(sources)
    fd = os.open(directory / "ask-capture.lock", os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("metrics_lock_must_be_private")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # No wait/retry for another capture.
        files = list(islice(directory.iterdir(), 4097)) + list(islice(sources.iterdir(), 4097))
        if len(files) > 4096 or sum(p.lstat().st_size for p in files) + len(raw) + LIMIT > 16 * 1024 * 1024:
            raise ValueError("ask_metrics_history_budget_reached")
        path = sources / digest
        try:
            target = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            if read_private(path, 16 * 1024) != raw:
                raise ValueError("ask_metrics_source_mismatch") from None
        else:
            with os.fdopen(target, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        observations = []
        for name, (metric, unit) in _FIELDS.items():
            value = source["measurements"][name]
            if value is not None and name == "cash_actual_microusd":
                value /= 1_000_000
            observations.append(
                Measurement(
                    metric=metric,
                    value=float(value) if value is not None else None,
                    unit=unit,
                    samples=int(value is not None),
                    scope=source["scope"],
                    model=source["model_ref"],
                    model_digest=source["weights_sha256"],
                    evidence="sources/" + digest,
                    evidence_sha256=digest,
                    reason=("UNMEASURED" if source["state"] == "COMPLETED" else "INCOMPLETE_RUN")
                    if value is None
                    else None,
                )
            )
        observations.append(
            Measurement(
                metric="quality.correct_fraction",
                value=None,
                unit=CATALOG["quality.correct_fraction"],
                samples=0,
                scope=source["scope"],
                evidence="sources/" + digest,
                evidence_sha256=digest,
                reason="UNMEASURED",
            )
        )
        snapshot = PerformanceSnapshot(
            captured_at=datetime.now(UTC),
            observations=tuple(observations),
            missing_areas=(
                "answer_accuracy",
                "retrieval_quality",
                "request_measurement_time",
                "runtime_build_source",
                "latency_distribution",
                "resource_samples",
                "provider_quota",
                "release_qualification",
            ),
        )
        saved = save_snapshot(directory, snapshot)
    finally:
        os.close(fd)
    return {
        "status": "SAVED",
        "snapshot": saved.name,
        "source_sha256": digest,
        "authority": "DERIVED_MEASUREMENTS_ONLY",
    }
