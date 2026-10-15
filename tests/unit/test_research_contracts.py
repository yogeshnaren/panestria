"""Contract bounds and inheritance are not proof of actual retained source data."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import SecretStr, ValidationError

from panestria.contracts.research import (
    MAX_SOURCE_BYTES,
    ClaimDraft,
    PassageRef,
    ResearchArtifactRef,
    ResearchLimits,
    ResearchRequestRecord,
    ResearchScope,
    SourceSnapshotRecord,
)


def scope():
    return ResearchScope(**{key: str(uuid4()) for key in ("owner_id", "project_id", "goal_id", "task_id")})


def artifact(task, **updates):
    return ResearchArtifactRef(
        artifact_id=str(uuid4()), task_id=task, sha256="ab" * 32, size_bytes=32, privacy_label="RESTRICTED", **updates
    )


def snapshot(**updates):
    actor = scope()
    body = dict(
        snapshot_id=str(uuid4()),
        request_id=str(uuid4()),
        scope=actor,
        requested_url="https://example.org/source",
        terminal_url="https://example.org/source",
        fetched_at=datetime.now(timezone.utc),
        http_status=200,
        content_type="text/plain",
        byte_limit=1024,
        query_label="INTERNAL",
        source_label="PUBLIC",
        raw=artifact(actor.task_id),
        text=artifact(actor.task_id),
        extractor_version="text-utf8-v1",
        completeness="COMPLETE",
    )
    return SourceSnapshotRecord(**{**body, **updates})


@pytest.mark.parametrize(
    "update",
    [
        {"schema_version": True},
        {"schema_version": 2},
        {"max_sources": True},
        {"max_sources": 17},
        {"max_redirects": 6},
        {"max_source_bytes": MAX_SOURCE_BYTES + 1},
        {"deadline_seconds": float("inf")},
        {"max_total_bytes": 1},
        {"approved": True},
        {"provider_credentials": "PRIVATE_SENTINEL"},
    ],
)
def test_limits_reject_implicit_authority_and_unbounded_inputs(update):
    with pytest.raises(ValidationError) as exc:
        ResearchLimits(**update)
    assert "PRIVATE_SENTINEL" not in str(exc.value)


@pytest.mark.parametrize(
    "update",
    [
        {"http_status": 404},
        {"raw": None},
        {"text": None},
        {"terminal_url": None},
        {"content_type": None},
        {"error_code": "size_limit"},
        {"byte_limit": 1},
        {"http_status": True},
        {"normalization_version": "invented"},
        {"fetched_at": datetime(2026, 1, 1)},
    ],
)
def test_complete_source_requires_observed_data_and_consistent_bounds(update):
    with pytest.raises(ValidationError):
        snapshot(**update)


@pytest.mark.parametrize("label", ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"])
def test_canonical_maximum_classification_cannot_be_downgraded(label):
    record = snapshot(query_label=label, source_label="PUBLIC")
    assert record.privacy_label == label
    with pytest.raises(ValidationError):
        SourceSnapshotRecord.model_validate({**record.model_dump(), "query_label": "UNKNOWN"})
    with pytest.raises(ValidationError):
        SourceSnapshotRecord.model_validate({**record.model_dump(), "privacy_label": "PUBLIC"})
    weaker = record.raw.model_copy(update={"privacy_label": "PUBLIC"})
    if label != "PUBLIC":
        with pytest.raises(ValidationError, match="research_artifact_label_downgrade"):
            SourceSnapshotRecord.model_validate({**record.model_dump(), "raw": weaker})


def test_reference_task_scope_and_serialized_schema_are_explicit():
    record = snapshot()
    assert SourceSnapshotRecord.model_validate_json(record.model_dump_json()) == record
    with pytest.raises(ValidationError, match="research_artifact_scope_mismatch"):
        SourceSnapshotRecord.model_validate({**record.model_dump(), "raw": artifact(str(uuid4()))})
    with pytest.raises(ValidationError, match="research_artifact_scope_mismatch"):
        ResearchRequestRecord(
            request_id=str(uuid4()), scope=record.scope, question=artifact(str(uuid4())), limits=ResearchLimits()
        )
    with pytest.raises(ValidationError):
        record.extractor_version = "changed"
    with pytest.raises(ValidationError):
        SourceSnapshotRecord.model_validate(
            {**record.model_dump(), "raw": record.raw.model_copy(update={"size_bytes": -1})}
        )


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "https://user:password@example.org/",
        "https://example.org/#anchor",
        "https://example.org/\nheader",
        "https://example.org:99999/",
    ],
)
def test_url_syntax_refuses_credentials_controls_or_ambiguous_reference(url):
    with pytest.raises(ValidationError, match="invalid_research_url"):
        snapshot(requested_url=url)


def test_url_syntax_does_not_pretend_to_establish_ssrf_or_fetch_authority():
    # Private-address denial, DNS rebinding, fetch retention and artifact hashes
    # require the actual broker/reader/resolver, not this data-only DTO.
    record = snapshot(requested_url="http://127.0.0.1/private")
    assert record.requested_url == "http://127.0.0.1/private"


def test_incomplete_and_unknown_source_facts_are_retained_without_inventing_them():
    record = snapshot(
        completeness="ERROR",
        raw=None,
        text=None,
        terminal_url=None,
        http_status=None,
        content_type=None,
        error_code="network_error",
    )
    assert record.raw is None and record.http_status is None and record.completeness == "ERROR"
    with pytest.raises(ValidationError, match="research_incomplete_reason_required"):
        snapshot(completeness="TRUNCATED")


def passage(**updates):
    return PassageRef(
        **{**dict(snapshot_id=str(uuid4()), request_id=str(uuid4()), text_sha256="ab" * 32, start=0, end=3), **updates}
    )


@pytest.mark.parametrize(
    "update",
    [
        {"start": -1},
        {"start": 3},
        {"end": 0},
        {"end": MAX_SOURCE_BYTES + 1},
        {"start": False},
        {"offset_unit": "character"},
        {"verified": True},
    ],
)
def test_passage_reference_bounds_are_half_open_bytes_and_no_verdict_authority(update):
    with pytest.raises(ValidationError):
        passage(**update)


def test_claims_are_masked_bounded_and_cannot_self_assert_support():
    draft = ClaimDraft(text=SecretStr("PRIVATE_SENTINEL"), kind="FACT", passages=(passage(),))
    assert "PRIVATE_SENTINEL" not in repr(draft) + draft.model_dump_json()
    with pytest.raises(ValidationError):
        ClaimDraft(text=SecretStr("x"), kind="FACT", support="SUPPORTED")
    with pytest.raises(ValidationError, match="research_claim_request_mismatch"):
        ClaimDraft(text=SecretStr("x"), kind="FACT", passages=(passage(), passage()))
    with pytest.raises(ValidationError, match="research_claim_byte_limit"):
        ClaimDraft(text=SecretStr("界" * 3000), kind="FACT")
