"""Pinned native startup and approved PUBLIC synthetic subscription tool request."""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import pytest
from test_registered_check_authority import configured as configured

from panestria.brokers.harness.claude_check import ClaudeRegisteredCheckAdapter
from panestria.brokers.harness.claude_proposal import PINNED_BINARY_SHA256, ClaudeProposalAdapter
from panestria.brokers.harness.cli_profile import BinaryPin
from panestria.brokers.harness.command_protocol import RegisteredCheckSession
from panestria.brokers.harness.event_parser import ClaudeEventParser, ProtocolRejected
from panestria.contracts.native_command import RegisteredCheckReceipt
from panestria.execution.registered_checks import RegisteredCheckController


def adapter():
    return ClaudeRegisteredCheckAdapter(
        ClaudeProposalAdapter(
            BinaryPin(Path("/home/yogesh/.local/share/claude/versions/2.1.273"), PINNED_BINARY_SHA256),
            Path.home() / ".panestria-native-claude",
            Path(__file__).resolve().parents[2] / "docs/specification/attachments/agentos-skills-v0.1.0.zip",
        )
    )


@pytest.mark.live
def test_pinned_native_zero_turn_startup_ignores_hostile_configuration(record_property):
    calls = []
    candidate = "snapshot:" + "ab" * 32
    session = RegisteredCheckSession(
        ("public-synthetic-check",),
        candidate,
        lambda *args: calls.append(args) or RegisteredCheckReceipt(outcome="DENIED"),
    )
    observation = adapter().check(session, candidate_ref=candidate, startup_only=True)
    assert observation.startup_observed and observation.hostile_configuration_ignored and not calls
    assert observation.process is None
    record_property("observation", json.dumps(asdict(observation), sort_keys=True))
    record_property("scope", "actual native MCP startup with fresh empty auth and zero turns, not inference")


@pytest.mark.live
@pytest.mark.parametrize("configured", ["native-public"], indirect=True)
def test_actual_subscription_native_check_reaches_durable_read_gateway(configured, monkeypatch, record_property):
    import panestria.brokers.harness.claude_check as launch

    task, args = configured
    controller = RegisteredCheckController(*args)
    rejected = []

    class ShapeParser(ClaudeEventParser):
        def _frame(self, raw):
            try:
                return super()._frame(raw)
            except ProtocolRejected:
                body = json.loads(raw)
                rejected.append(
                    {
                        "type": body.get("type"),
                        "keys": sorted(body),
                        "message_keys": sorted(body.get("message", {}))
                        if isinstance(body.get("message"), dict)
                        else [],
                        "block_keys": [
                            sorted(block)
                            for block in body.get("message", {}).get("content", [])
                            if isinstance(block, dict)
                        ]
                        if isinstance(body.get("message"), dict)
                        else [],
                        "tool_result_shape": sorted(body["tool_use_result"])
                        if isinstance(body.get("tool_use_result"), dict)
                        else type(body.get("tool_use_result")).__name__,
                        "sha256": hashlib.sha256(raw).hexdigest(),
                    }
                )
                raise

    monkeypatch.setattr(launch, "ClaudeEventParser", ShapeParser)
    observation = adapter().check(controller.session(), candidate_ref=controller.candidate_ref)
    record_property("observation", json.dumps(asdict(observation), sort_keys=True))
    record_property("rejected_frame_shapes", json.dumps(rejected, sort_keys=True))
    assert observation.process is not None
    assert observation.process.status == "CANDIDATE", (asdict(observation), rejected)
    assert observation.startup_observed and observation.hostile_configuration_ignored
    with controller.connect() as connection:
        rows = connection.execute(
            "SELECT state,receipt_sha256 FROM panestria.worker_invocation WHERE task_id=%s", (task["task"],)
        ).fetchall()
        assert len(rows) == 1 and rows[0][0] == "RETURNED"
        report = json.loads(controller.reports.read_blob(str(rows[0][1]).strip()))
        assert report["kind"] == "registered-read-check" and report["exit_code"] == 0
        assert connection.execute(
            "SELECT count(*) FROM panestria.task_event WHERE task_id=%s AND kind='invocation.claimed'", (task["task"],)
        ).fetchone() == (1,)
        assert connection.execute("SELECT state FROM panestria.task WHERE id=%s", (task["task"],)).fetchone() == (
            "RUNNING",
        )
    record_property(
        "scope",
        "PUBLIC synthetic Claude subscription check through actual PG/Docker/report; no owner acceptance",
    )
    record_property("native_actual_cash", "UNKNOWN_SUBSCRIPTION_ESTIMATE_ONLY_NO_DIRECT_SDK_CALL")
