"""Opted-in PUBLIC synthetic corpus only; no private claim or support/release promotion."""

import os
from pathlib import Path

import pytest

from panestria.brokers.harness.claude_proposal import PINNED_BINARY_SHA256
from panestria.brokers.harness.cli_profile import BinaryPin
from panestria.execution.native_entailment_probe import NativeEntailmentProbe, native_observation_json


@pytest.mark.live
@pytest.mark.parametrize("fold", ["calibration", "qualification"])
def test_actual_public_fixture_subscription_observation(fold, record_property):
    if os.environ.get("PANESTRIA_RUN_NATIVE_ENTAILMENT") != "1":
        pytest.skip("explicit existing-login PUBLIC fixture opt-in absent; actual observation not run")
    root = Path(__file__).resolve().parents[2]
    probe = NativeEntailmentProbe(
        BinaryPin(Path.home() / ".local/share/claude/versions/2.1.273", PINNED_BINARY_SHA256),
        Path.home() / ".panestria-native-claude",
        root / "docs/specification/attachments/agentos-skills-v0.1.0.zip",
        native_model=os.environ.get("PANESTRIA_NATIVE_ENTAILMENT_MODEL"),
    )
    result = probe.run(root / "tests/fixtures/research/snli-v1/corpus.json", fold)
    record_property("public_native_entailment_observation", native_observation_json(result))
    assert result.status == "COMPLETE", result.reason
    assert len(result.predictions) == 36
    assert result.model == (probe.native_model or "claude-haiku-4-5-20251001")
    assert result.cash_actual_microusd is None and result.observed_overage is not True
    record_property(
        "scope",
        "actual PUBLIC subscription corpus observation only; no private payload, semantic/policy/release authority",
    )
