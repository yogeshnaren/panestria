"""Exact Unicode/byte integrity does not certify fetched sources or semantic support."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from panestria.contracts.research import (
    MAX_SOURCE_BYTES,
    PassageRef,
    ResearchArtifactRef,
    ResearchScope,
    SourceSnapshotRecord,
)
from panestria.verification import research_text
from panestria.verification.research_text import ResearchTextRejected, normalize_plain_utf8, validate_passage_bytes


def sha(raw):
    import hashlib

    return hashlib.sha256(raw).hexdigest()


DEFAULT_TEXT = "Aé🙂Z".encode()


def records(text=DEFAULT_TEXT):
    scope = ResearchScope(**{key: str(uuid4()) for key in ("owner_id", "project_id", "goal_id", "task_id")})
    artifact = ResearchArtifactRef(
        artifact_id=str(uuid4()),
        task_id=scope.task_id,
        sha256=sha(text),
        size_bytes=len(text),
        privacy_label="RESTRICTED",
    )
    source = SourceSnapshotRecord(
        snapshot_id=str(uuid4()),
        request_id=str(uuid4()),
        scope=scope,
        requested_url="https://example.org/a",
        terminal_url="https://example.org/a",
        fetched_at=datetime.now(UTC),
        http_status=200,
        content_type="text/plain",
        byte_limit=1024,
        query_label="INTERNAL",
        source_label="PUBLIC",
        raw=artifact,
        text=artifact,
        extractor_version="text-utf8-v1",
        completeness="COMPLETE",
    )
    reference = PassageRef(
        snapshot_id=source.snapshot_id, request_id=source.request_id, text_sha256=sha(text), start=1, end=7
    )
    return source, reference, text


def test_nfc_preserves_line_endings_bom_case_whitespace_and_masks_repr():
    raw = "\ufeff  Cafe\u0301\r\nCase\r\t下一行\n".encode()
    result = normalize_plain_utf8(raw, expected_raw_sha256=sha(raw), byte_limit=1024)
    assert result.data == "\ufeff  Café\r\nCase\r\t下一行\n".encode()
    assert result.raw_sha256 == sha(raw) and result.text_sha256 == sha(result.data)
    assert result.raw_sha256 != result.text_sha256
    assert "Café" not in repr(result)
    assert (
        normalize_plain_utf8(result.data, expected_raw_sha256=result.text_sha256, byte_limit=1024).data == result.data
    )


@pytest.mark.parametrize(
    "raw", [b"", b"\xff", b"\xc0\xaf", b"\xed\xa0\x80", b"\xf0\x9f", b"a" * (MAX_SOURCE_BYTES + 1)]
)
def test_invalid_or_oversized_utf8_fails_without_input_disclosure(raw):
    with pytest.raises(ResearchTextRejected):
        normalize_plain_utf8(raw, expected_raw_sha256=sha(raw), byte_limit=MAX_SOURCE_BYTES)


@pytest.mark.parametrize("limit", [True, 0, -1, 1.0, MAX_SOURCE_BYTES + 1])
def test_declared_caps_are_exact_bounded_integers(limit):
    with pytest.raises(ResearchTextRejected, match="byte_limit"):
        normalize_plain_utf8(b"public", expected_raw_sha256=sha(b"public"), byte_limit=limit)


def test_normalization_expansion_must_also_fit_cap():
    # U+0344 NFC expands into two combining code points (four UTF-8 bytes).
    raw = "\u0344".encode()
    with pytest.raises(ResearchTextRejected, match="byte_limit"):
        normalize_plain_utf8(raw, expected_raw_sha256=sha(raw), byte_limit=len(raw))


@pytest.mark.parametrize("digest", ["ab" * 32, "X" * 64, "", None])
def test_raw_hash_must_match_before_extraction(digest):
    with pytest.raises(ResearchTextRejected):
        normalize_plain_utf8(b"public", expected_raw_sha256=digest, byte_limit=1024)


def test_unknown_unicode_runtime_is_not_silently_renormalized(monkeypatch):
    monkeypatch.setattr(research_text.unicodedata, "unidata_version", "99.0.0")
    with pytest.raises(ResearchTextRejected, match="unsupported_unicode"):
        normalize_plain_utf8(b"public", expected_raw_sha256=sha(b"public"), byte_limit=1024)


def test_passage_uses_half_open_utf8_bytes_and_never_grants_fetch_or_support_authority():
    source, reference, text = records()
    match = validate_passage_bytes(source, reference, text)
    assert match.text.get_secret_value() == "é🙂"
    assert match.privacy_label == "RESTRICTED"  # Stronger text label survives.
    assert match.verdict == "BYTE_MATCH_ONLY_FETCH_AUTHORITY_REQUIRED"
    assert "é🙂" not in repr(match)


@pytest.mark.parametrize("start,end", [(2, 7), (1, 4), (4, 6), (0, 9)])
def test_split_characters_and_out_of_range_offsets_rejected(start, end):
    source, reference, text = records()
    with pytest.raises(ResearchTextRejected):
        validate_passage_bytes(source, reference.model_copy(update={"start": start, "end": end}), text)


@pytest.mark.parametrize(
    "changes",
    [
        {"snapshot_id": str(uuid4())},
        {"request_id": str(uuid4())},
        {"text_sha256": "ef" * 32},
        {"normalization_version": "future"},
        {"start": True},
        {"start": 7, "end": 1},
    ],
)
def test_substitution_and_unvalidated_copies_do_not_bypass_bindings(changes):
    source, reference, text = records()
    with pytest.raises(ResearchTextRejected):
        validate_passage_bytes(source, reference.model_copy(update=changes), text)


@pytest.mark.parametrize("text", [b"A" * 8, "Aé🙂ZZ".encode(), b"\xff" * 8])
def test_corrupted_or_length_changed_complete_text_rejected(text):
    source, reference, _ = records()
    with pytest.raises(ResearchTextRejected):
        validate_passage_bytes(source, reference, text)


def test_hash_matching_noncanonical_text_still_rejected():
    source, reference, text = records("Ae\u0301🙂Z".encode())
    with pytest.raises(ResearchTextRejected, match="noncanonical"):
        validate_passage_bytes(source, reference, text)


@pytest.mark.parametrize(
    "status,error", [("TRUNCATED", "size_limit"), ("ERROR", "network_error"), ("UNSUPPORTED", "extractor_unsupported")]
)
def test_incomplete_sources_cannot_supply_passages_even_when_bytes_match(status, error):
    source, reference, text = records()
    with pytest.raises(ResearchTextRejected, match="incomplete"):
        validate_passage_bytes(source.model_copy(update={"completeness": status, "error_code": error}), reference, text)


def test_changed_nested_artifact_scope_is_revalidated():
    source, reference, text = records()
    forged = source.text.model_copy(update={"task_id": str(uuid4())})
    with pytest.raises(ResearchTextRejected, match="invalid_research_record"):
        validate_passage_bytes(source.model_copy(update={"text": forged}), reference, text)
