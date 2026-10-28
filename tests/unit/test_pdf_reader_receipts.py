"""Injected PDF protocol guards only; these do not qualify actual OS isolation."""

import base64
import hashlib
import json
from pathlib import Path

import pytest

import panestria.brokers.research.reader as module
from panestria.brokers.research.pdf_bundle import PDF_EXTRACTOR, PYPDF_BUNDLE_SHA256, PdfBundleUnavailable
from panestria.brokers.research.reader import IsolatedTextReader
from panestria.sandbox.runner import DockerSandbox, SandboxReceipt


@pytest.mark.parametrize(
    "change",
    [
        "bundle",
        "tokenizer",
        "missing-limitation",
        "extra-limitation",
        "first-start",
        "end",
        "bool",
        "separator",
        "utf8",
        "page-count",
        "missing-field",
    ],
)
def test_pdf_receipt_must_bind_bundle_limitations_and_exact_utf8_page_spans(monkeypatch, change):
    raw, text = b"%PDF-synthetic-injected-protocol", "é\n\f\npage"
    encoded = text.encode()
    body = {
        "outcome": "COMPLETE",
        "reason": "extracted_text_only",
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_size": len(raw),
        "text_sha256": hashlib.sha256(encoded).hexdigest(),
        "text_size": len(encoded),
        "text_b64": base64.b64encode(encoded).decode(),
        "extractor_version": PDF_EXTRACTOR,
        "normalization_version": "nfc-utf8-v1",
        "unicode_version": "15.0.0",
        "tokenizer_sha256": PYPDF_BUNDLE_SHA256,
        "pdf_bundle_sha256": PYPDF_BUNDLE_SHA256,
        "page_spans": [[0, 2], [5, 9]],
        "limitations": list(module.pdf_worker.LIMITATIONS),
    }
    if change in {"bundle", "tokenizer"}:
        body["pdf_bundle_sha256" if change == "bundle" else "tokenizer_sha256"] = "ab" * 32
    elif change == "missing-limitation":
        body["limitations"] = ["pdf-no-ocr"]
    elif change == "extra-limitation":
        body["limitations"].append("approved-by-owner")
    elif change == "first-start":
        body["page_spans"][0][0] = 1
    elif change == "end":
        body["page_spans"][1][1] = 8
    elif change == "bool":
        body["page_spans"][0][0] = False
    elif change == "separator":
        body["page_spans"] = [[0, 2], [4, 9]]
    elif change == "utf8":
        body["page_spans"][0][1] = 1
    elif change == "page-count":
        body["page_spans"] *= 33
    elif change == "missing-field":
        del body["page_spans"]

    def synthetic(_self, _workspace, _argv, profile, **_kwargs):
        return SandboxReceipt(
            "EXPLICIT_SYNTHETIC", profile.sha256(), "cd" * 32, 0, "completed", json.dumps(body).encode(), 0.0, False
        )

    monkeypatch.setattr(DockerSandbox, "run", synthetic)
    result = IsolatedTextReader().extract(
        raw, expected_sha256=hashlib.sha256(raw).hexdigest(), content_type="application/pdf"
    )
    assert result.outcome == "UNKNOWN" and result.text is None


@pytest.mark.parametrize("when", ["before", "after"])
def test_pdf_bundle_unconfirmed_never_falls_back_to_unconfined_reader(monkeypatch, when):
    calls = []

    def unavailable(*_args, **_kwargs):
        raise PdfBundleUnavailable("synthetic")

    def synthetic(*_args, **_kwargs):
        calls.append(True)
        return object()

    monkeypatch.setattr(module, "stage_pdf_bundle" if when == "before" else "verify_pdf_bundle", unavailable)
    monkeypatch.setattr(DockerSandbox, "run", synthetic)
    raw = b"%PDF-synthetic"
    result = IsolatedTextReader().extract(
        raw, expected_sha256=hashlib.sha256(raw).hexdigest(), content_type="application/pdf"
    )
    assert result.outcome == "UNKNOWN" and result.text is None
    assert len(calls) == (0 if when == "before" else 1)


def test_in_container_worker_pins_match_the_host_bundle() -> None:
    from panestria.brokers.research import pdf_bundle, pdf_worker

    assert pdf_worker.BUNDLE_SHA256 == pdf_bundle.PYPDF_BUNDLE_SHA256
    source = Path(pdf_worker.__file__).read_text(encoding="utf-8")
    assert f'pypdf.__version__ != "{pdf_bundle.PYPDF_VERSION}"' in source
    assert f'"extractor_version": "{PDF_EXTRACTOR}"' in source


def test_receipts_from_the_previous_pinned_extractor_stay_verifiable() -> None:
    from panestria.brokers.research.pdf_bundle import PDF_EXTRACTOR_BUNDLES

    assert PDF_EXTRACTOR_BUNDLES["pypdf-6.20.1-text-v1"] == (
        "ee7677af7c459d97f4d1ee9a715e5b4d19fecb3295d2d596b6d4a6ac076b6c5a"
    )
    assert PDF_EXTRACTOR_BUNDLES[PDF_EXTRACTOR] == PYPDF_BUNDLE_SHA256
