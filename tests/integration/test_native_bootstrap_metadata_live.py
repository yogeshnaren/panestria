"""Opted-in actual pinned binary version/help, no auth/profile/gateway/model call."""

import dataclasses
import json
import os
from pathlib import Path

import pytest

from panestria.brokers.harness.claude_proposal import PINNED_BINARY_SHA256
from panestria.brokers.harness.cli_profile import BinaryPin
from panestria.brokers.harness.native_bootstrap import NativeBootstrap


@pytest.mark.live
def test_actual_pinned_claude_version_and_help_run_in_offline_os_envelope(record_property):
    if os.environ.get("PANESTRIA_RUN_NATIVE_BOOTSTRAP_METADATA") != "1":
        pytest.skip("explicit native credential-free metadata opt-in absent")
    observation = NativeBootstrap().inspect(
        BinaryPin(Path("/home/yogesh/.local/share/claude/versions/2.1.273"), PINNED_BINARY_SHA256)
    )
    assert observation.status == "BOOTSTRAP_ONLY" and len(observation.runs) == 2
    assert (
        not observation.runtime_authority
        and not observation.authentication_observed
        and not observation.inference_observed
    )
    record_property(
        "scope", "two actual pinned version/help metadata processes in offline OS envelope; no auth/inference"
    )
    record_property("observation", json.dumps(dataclasses.asdict(observation), sort_keys=True))
