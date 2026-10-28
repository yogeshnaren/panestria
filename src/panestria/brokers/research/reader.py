"""Bounded fixed reader inside the existing actual Docker sandbox, not source authority."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import tempfile
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import SecretStr

from panestria.brokers.research import pdf_worker, reader_worker
from panestria.brokers.research.pdf_bundle import (
    PDF_EXTRACTOR,
    PYPDF_BUNDLE_SHA256,
    stage_pdf_bundle,
    verify_pdf_bundle,
)
from panestria.contracts.research import MAX_SOURCE_BYTES
from panestria.sandbox.profiles import ReadOnlyMount, SandboxProfile
from panestria.sandbox.runner import DockerSandbox


@dataclass(frozen=True)
class ReaderObservation:
    outcome: Literal["COMPLETE", "TRUNCATED", "ERROR", "UNSUPPORTED", "UNKNOWN", "CANCELLED"]
    reason: str
    text: SecretStr | None = None
    text_sha256: str | None = None
    extractor_version: str | None = None
    tokenizer_sha256: str | None = None
    sandbox_profile_sha256: str | None = None
    reader_program_sha256: str | None = None
    effective_config_sha256: str | None = None
    pdf_bundle_sha256: str | None = None
    page_spans: tuple[tuple[int, int], ...] = ()
    limitations: tuple[str, ...] = ()
    raw_sha256: str | None = None
    raw_size_bytes: int | None = None
    hidden_bytes_dropped: int | None = None


def _closed_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


class IsolatedTextReader:
    def extract(
        self,
        raw: bytes,
        *,
        expected_sha256: str,
        content_type: str,
        max_text_bytes: int = 512 * 1024,
        cancel: threading.Event | None = None,
    ) -> ReaderObservation:
        if (
            type(raw) is not bytes
            or len(raw) > MAX_SOURCE_BYTES
            or type(expected_sha256) is not str
            or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)
            or hashlib.sha256(raw).hexdigest() != expected_sha256
            or type(content_type) is not str
            or content_type not in {"text/plain", "text/html", "application/pdf", "application/octet-stream"}
            or type(max_text_bytes) is not int
            or not 1 <= max_text_bytes <= 512 * 1024
        ):
            return ReaderObservation("ERROR", "invalid_reader_input")
        cancel = cancel if cancel is not None else threading.Event()
        if cancel.is_set():
            return ReaderObservation("CANCELLED", "cancelled_before_reader")
        try:
            with tempfile.TemporaryDirectory(prefix="panestria-reader-", dir="/tmp") as folder:
                root = Path(folder)
                workspace = root / "workspace"
                workspace.mkdir(mode=0o700)
                source, script = root / "source.bin", root / "reader.py"
                source.write_bytes(raw)
                is_pdf = content_type == "application/pdf"
                bundle = stage_pdf_bundle(root / "pdf-deps") if is_pdf else None
                worker = pdf_worker if is_pdf else reader_worker
                program_path = worker.__file__
                if program_path is None:
                    raise ValueError
                program = Path(program_path).read_bytes()
                script.write_bytes(program)
                source.chmod(0o444)
                script.chmod(0o444)
                program_sha = hashlib.sha256(program).hexdigest()
                profile = SandboxProfile(
                    name="read-only-research",
                    uid=os.getuid(),
                    gid=os.getgid(),
                    wall_seconds=10,
                    output_bytes=1024 * 1024,
                )
                runner = DockerSandbox(
                    root,
                    runtime_mounts=(
                        ReadOnlyMount(source, "/runtime/source.bin"),
                        ReadOnlyMount(script, "/runtime/reader.py"),
                        *((ReadOnlyMount(bundle.directory, "/runtime/pdf-deps"),) if bundle else ()),
                    ),
                )
                receipt = runner.run(
                    workspace,
                    (
                        "/usr/local/bin/python",
                        "-I",
                        "-B",
                        "/runtime/reader.py",
                        expected_sha256,
                        content_type,
                        str(len(raw)),
                        str(max_text_bytes),
                    ),
                    profile,
                    cancel=cancel,
                )
                if bundle is not None:
                    verify_pdf_bundle(bundle)
                if cancel.is_set():
                    return ReaderObservation("CANCELLED", "reader_cancelled")
                if (
                    receipt.reason != "completed"
                    or receipt.exit_code != 0
                    or receipt.oom_killed
                    or receipt.profile_sha256 != profile.sha256()
                    or not re.fullmatch(r"[0-9a-f]{64}", receipt.effective_config_sha256)
                    or len(receipt.output) > 1024 * 1024
                    or hashlib.sha256(source.read_bytes()).hexdigest() != expected_sha256
                    or hashlib.sha256(script.read_bytes()).hexdigest() != program_sha
                ):
                    return ReaderObservation("UNKNOWN", "reader_execution_unconfirmed")
                body = json.loads(receipt.output.decode("utf-8"), object_pairs_hook=_closed_pairs)
                if not isinstance(body, dict):
                    raise ValueError
                if body.get("outcome") != "COMPLETE":
                    valid = {
                        "TRUNCATED": {"text_byte_limit", "pdf_page_limit"} if is_pdf else "text_byte_limit",
                        "ERROR": {"decoder_error", "reader_error"},
                        "UNSUPPORTED": {"pdf_encrypted", "pdf_feature_unsupported", "pdf_no_text"}
                        if is_pdf
                        else "extractor_unsupported",
                    }
                    outcome, reason = body.get("outcome"), body.get("reason")
                    if set(body) != {"outcome", "reason"} or outcome not in valid or not isinstance(reason, str):
                        raise ValueError
                    expected = valid[outcome]
                    if reason != expected and (not isinstance(expected, set) or reason not in expected):
                        raise ValueError
                    return ReaderObservation(
                        outcome,
                        reason,
                        sandbox_profile_sha256=profile.sha256(),
                        reader_program_sha256=program_sha,
                        effective_config_sha256=receipt.effective_config_sha256,
                    )
                pdf_keys = {"pdf_bundle_sha256", "page_spans", "limitations"} if is_pdf else set()
                html_keys = {"hidden_bytes_dropped"} if content_type == "text/html" else set()
                if set(body) != pdf_keys | html_keys | {
                    "outcome",
                    "reason",
                    "raw_sha256",
                    "raw_size",
                    "text_sha256",
                    "text_size",
                    "text_b64",
                    "extractor_version",
                    "normalization_version",
                    "unicode_version",
                    "tokenizer_sha256",
                }:
                    raise ValueError
                text_bytes = base64.b64decode(body["text_b64"], validate=True)
                text = text_bytes.decode("utf-8", errors="strict")
                extractor = {
                    "text/plain": "strict-utf8-v1",
                    "text/html": reader_worker.HTML_EXTRACTOR,
                    "application/pdf": PDF_EXTRACTOR,
                }.get(content_type)
                if extractor is None:
                    raise ValueError
                if (
                    body["reason"] != "extracted_text_only"
                    or body["raw_sha256"] != expected_sha256
                    or type(body["raw_size"]) is not int
                    or body["raw_size"] != len(raw)
                    or type(body["text_size"]) is not int
                    or body["text_size"] != len(text_bytes)
                    or len(text_bytes) > max_text_bytes
                    or body["text_sha256"] != hashlib.sha256(text_bytes).hexdigest()
                    or body["extractor_version"] != extractor
                    or body["normalization_version"] != "nfc-utf8-v1"
                    or body["unicode_version"] != "15.0.0"
                    or unicodedata.unidata_version != "15.0.0"
                    or unicodedata.normalize("NFC", text) != text
                    or type(body["tokenizer_sha256"]) is not str
                    or not re.fullmatch(r"[0-9a-f]{64}", body["tokenizer_sha256"])
                    or (
                        html_keys
                        and (
                            type(body["hidden_bytes_dropped"]) is not int
                            or not 0 <= body["hidden_bytes_dropped"] <= len(raw)
                        )
                    )
                ):
                    raise ValueError
                spans: tuple[tuple[int, int], ...] = ()
                if is_pdf:
                    if (
                        body["pdf_bundle_sha256"] != PYPDF_BUNDLE_SHA256
                        or body["tokenizer_sha256"] != PYPDF_BUNDLE_SHA256
                        or body["limitations"] != list(pdf_worker.LIMITATIONS)
                        or type(body["page_spans"]) is not list
                        or not 1 <= len(body["page_spans"]) <= 32
                    ):
                        raise ValueError
                    previous = -3
                    checked = []
                    for span in body["page_spans"]:
                        if type(span) is not list or len(span) != 2 or any(type(value) is not int for value in span):
                            raise ValueError
                        start, end = span
                        if not (start == previous + 3 and start < end <= len(text_bytes)):
                            raise ValueError
                        if start and text_bytes[previous:start] != pdf_worker.SEPARATOR:
                            raise ValueError
                        if not text_bytes[start:end].decode("utf-8", errors="strict").strip():
                            raise ValueError
                        checked.append((start, end))
                        previous = end
                    if previous != len(text_bytes):
                        raise ValueError
                    spans = tuple(checked)
                return ReaderObservation(
                    "COMPLETE",
                    "extracted_text_only",
                    SecretStr(text),
                    body["text_sha256"],
                    extractor,
                    body["tokenizer_sha256"],
                    profile.sha256(),
                    program_sha,
                    receipt.effective_config_sha256,
                    pdf_bundle_sha256=PYPDF_BUNDLE_SHA256 if is_pdf else None,
                    page_spans=spans,
                    limitations=pdf_worker.LIMITATIONS if is_pdf else (),
                    raw_sha256=expected_sha256,
                    raw_size_bytes=len(raw),
                    hidden_bytes_dropped=body["hidden_bytes_dropped"] if html_keys else None,
                )
        except Exception:
            return ReaderObservation("UNKNOWN", "reader_unavailable")
