"""Deterministic byte integrity only; no fetch provenance or claim authority."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Literal

from pydantic import SecretStr, ValidationError

from panestria.contracts.classification import CanonicalClass, derive_classification
from panestria.contracts.research import MAX_SOURCE_BYTES, NORMALIZATION, PassageRef, SourceSnapshotRecord

UNICODE_VERSION = "15.0.0"


class ResearchTextRejected(ValueError):
    pass


@dataclass(frozen=True)
class NormalizedText:
    raw_sha256: str
    text_sha256: str
    data: bytes = field(repr=False)
    normalization_version: Literal["nfc-utf8-v1"] = NORMALIZATION


@dataclass(frozen=True)
class PassageByteMatch:
    snapshot_id: str
    request_id: str
    start: int
    end: int
    text: SecretStr
    privacy_label: CanonicalClass
    verdict: Literal["BYTE_MATCH_ONLY_FETCH_AUTHORITY_REQUIRED"] = "BYTE_MATCH_ONLY_FETCH_AUTHORITY_REQUIRED"


def _text(raw: bytes) -> str:
    if unicodedata.unidata_version != UNICODE_VERSION:
        raise ResearchTextRejected("unsupported_unicode_version")
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_SOURCE_BYTES:
        raise ResearchTextRejected("research_text_byte_limit")
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeError:
        raise ResearchTextRejected("invalid_utf8") from None


def normalize_plain_utf8(raw: bytes, *, expected_raw_sha256: str, byte_limit: int) -> NormalizedText:
    """Plain UTF-8 only. The caller must establish MIME/extractor/fetch authority."""
    if type(byte_limit) is not int or not 1 <= byte_limit <= MAX_SOURCE_BYTES:
        raise ResearchTextRejected("research_text_byte_limit")
    if type(raw) is not bytes or not 0 < len(raw) <= byte_limit:
        raise ResearchTextRejected("research_text_byte_limit")
    if not isinstance(expected_raw_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_raw_sha256):
        raise ResearchTextRejected("invalid_raw_hash")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_raw_sha256:
        raise ResearchTextRejected("raw_hash_mismatch")
    normalized = unicodedata.normalize("NFC", _text(raw)).encode("utf-8")
    if len(normalized) > byte_limit:
        raise ResearchTextRejected("research_text_byte_limit")
    return NormalizedText(digest, hashlib.sha256(normalized).hexdigest(), normalized)


def validate_passage_bytes(snapshot: SourceSnapshotRecord, reference: PassageRef, text: bytes) -> PassageByteMatch:
    """Verify supplied bytes; this is deliberately not a protected SourceStore resolver."""
    try:
        snapshot = SourceSnapshotRecord.model_validate(snapshot)
        reference = PassageRef.model_validate(reference)
    except ValidationError:
        raise ResearchTextRejected("invalid_research_record") from None
    if snapshot.completeness != "COMPLETE" or snapshot.text is None:
        raise ResearchTextRejected("incomplete_source")
    if (
        reference.snapshot_id != snapshot.snapshot_id
        or reference.request_id != snapshot.request_id
        or reference.normalization_version != snapshot.normalization_version
        or reference.text_sha256 != snapshot.text.sha256
    ):
        raise ResearchTextRejected("research_reference_mismatch")
    decoded = _text(text)
    if len(text) != snapshot.text.size_bytes or hashlib.sha256(text).hexdigest() != snapshot.text.sha256:
        raise ResearchTextRejected("text_hash_or_length_mismatch")
    if unicodedata.normalize("NFC", decoded) != decoded:
        raise ResearchTextRejected("noncanonical_text")
    if reference.end > len(text):
        raise ResearchTextRejected("passage_out_of_range")
    try:
        passage = text[reference.start : reference.end].decode("utf-8", errors="strict")
    except UnicodeError:
        raise ResearchTextRejected("passage_splits_utf8_character") from None
    label = derive_classification((snapshot.privacy_label, snapshot.text.privacy_label)).effective
    assert label is not None
    return PassageByteMatch(
        snapshot.snapshot_id, snapshot.request_id, reference.start, reference.end, SecretStr(passage), label
    )
