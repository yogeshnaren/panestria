"""Injected runner receipts test parser guards only, never actual OS conformance."""

import base64
import hashlib
import json
from dataclasses import replace

import pytest

from panestria.brokers.research.reader import IsolatedTextReader
from panestria.sandbox.runner import DockerSandbox, SandboxReceipt


@pytest.mark.parametrize(
    "change",
    [
        "raw-hash",
        "size-bool",
        "text-hash",
        "nfc",
        "unicode",
        "extra-authority",
        "bad-base64",
        "tokenizer",
        "normalization",
        "duplicate",
        "runtime",
        "effective",
    ],
)
def test_forged_or_corrupt_reader_protocol_never_exposes_complete_text(monkeypatch, change):
    raw = b"public synthetic"
    text = "text"
    if change == "nfc":
        text = "e\u0301"
    encoded = text.encode()
    body = {
        "outcome": "COMPLETE",
        "reason": "extracted_text_only",
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_size": len(raw),
        "text_sha256": hashlib.sha256(encoded).hexdigest(),
        "text_size": len(encoded),
        "text_b64": base64.b64encode(encoded).decode(),
        "extractor_version": "strict-utf8-v1",
        "normalization_version": "nfc-utf8-v1",
        "unicode_version": "15.0.0",
        "tokenizer_sha256": "ab" * 32,
    }
    if change == "raw-hash":
        body["raw_sha256"] = "00" * 32
    elif change == "size-bool":
        body["text_size"] = True
    elif change == "text-hash":
        body["text_sha256"] = "00" * 32
    elif change == "unicode":
        body["unicode_version"] = "16.0.0"
    elif change == "extra-authority":
        body["approved"] = True
    elif change == "bad-base64":
        body["text_b64"] = "!invalid"
    elif change == "tokenizer":
        body["tokenizer_sha256"] = "unknown"
    elif change == "normalization":
        body["normalization_version"] = "unknown"
    output = json.dumps(body).encode()
    if change == "duplicate":
        output = output[:-1] + b',"outcome":"COMPLETE"}'

    def synthetic(_self, _workspace, _argv, profile, **_kwargs):
        receipt = SandboxReceipt(
            "EXPLICIT_SYNTHETIC_FIXTURE", profile.sha256(), "cd" * 32, 0, "completed", output, 0.0, False
        )
        if change == "runtime":
            receipt = replace(receipt, reason="deadline_exceeded")
        elif change == "effective":
            receipt = replace(receipt, effective_config_sha256="not-proven")
        return receipt

    monkeypatch.setattr(DockerSandbox, "run", synthetic)
    result = IsolatedTextReader().extract(
        raw, expected_sha256=hashlib.sha256(raw).hexdigest(), content_type="text/plain"
    )
    assert result.outcome == "UNKNOWN" and result.text is None
