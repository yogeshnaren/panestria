"""Actual subprocess/parser metadata transport, with synthetic JSON, no inference."""

import json
import sys

import pytest

from panestria.brokers.harness.event_parser import ClaudeEventParser
from panestria.brokers.harness.process_runner import collect_native


@pytest.mark.parametrize("model", ["claude-haiku-4-5-20251001", None, "unsafe\nlabel"])
def test_original_init_identity_survives_real_process_receipt_without_acceptance(tmp_path, model):
    init = {"type": "system", "subtype": "init", "session_id": "synthetic"}
    if model is not None:
        init["model"] = model
    result = {"type": "result", "subtype": "success", "is_error": False, "result": "synthetic"}
    wire = "\n".join(json.dumps(frame) for frame in (init, result)) + "\n"
    receipt = collect_native(
        (sys.executable, "-c", "import sys; sys.stdout.write(sys.argv[1])", wire),
        tmp_path,
        {},
        ClaudeEventParser(),
        wall_seconds=3,
    )
    if model == "unsafe\nlabel":
        assert receipt.status == "REJECTED" and receipt.reason == "invalid_model_metadata"
        assert receipt.result is None
    else:
        assert receipt.status == "CANDIDATE" and receipt.result is not None
        assert receipt.result.reported_init_model == model
        assert receipt.result.accepted is False
