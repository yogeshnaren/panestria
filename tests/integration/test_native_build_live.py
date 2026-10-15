"""Actual native subscription + PG + Docker + Git; scripted approval is synthetic."""

from __future__ import annotations

import hashlib
import os
import subprocess
import threading
import time
from pathlib import Path
from uuid import uuid4

import pytest

from panestria.brokers.harness.claude_proposal import PINNED_BINARY_SHA256, ClaudeProposalAdapter, ProposalReceipt
from panestria.brokers.harness.cli_profile import BinaryPin
from panestria.contracts.native_proposal import PROMPT_SHA256
from panestria.execution.proposal_demo import ProposalDemo, _git
from panestria.kernel.errors import KernelDenied
from panestria.sandbox.profiles import DEFAULT_IMAGE

ROOT = Path(__file__).resolve().parents[2]


class ObservedNativeAdapter(ClaudeProposalAdapter):
    """Retain only bounded transport facts, never replace real provider results."""

    def __init__(self) -> None:
        super().__init__(
            BinaryPin(Path("/home/yogesh/.local/share/claude/versions/2.1.273"), PINNED_BINARY_SHA256),
            Path.home() / ".panestria-native-claude",
            ROOT / "docs/specification/attachments/agentos-skills-v0.1.0.zip",
        )
        self.observations: list[tuple[str, bool, str]] = []

    def propose(self, *, wall_seconds: float = 90, cancel: threading.Event | None = None) -> ProposalReceipt:
        receipt = super().propose(wall_seconds=wall_seconds, cancel=cancel)
        self.observations.append(
            (receipt.status, bool(receipt.process.result and receipt.process.result.accepted), receipt.process.stdout_sha256)
        )
        return receipt


@pytest.mark.live
def test_actual_native_candidate_is_verified_then_exact_test_approval_merges(
    r1_database: str, tmp_path: Path, record_property: pytest.RecordProperty
) -> None:
    assert os.environ.get("PANESTRIA_ALLOW_NATIVE_LIVE") == "1", "explicit native live opt-in required"
    # A qualification must never download an image as an implicit prerequisite.
    cached = subprocess.run(["docker", "image", "inspect", DEFAULT_IMAGE], capture_output=True, timeout=10)
    assert cached.returncode == 0, "cached pinned worker image required"
    adapter = ObservedNativeAdapter()
    assert hashlib.sha256(adapter.pin.path.read_bytes()).hexdigest() == PINNED_BINARY_SHA256
    record_property("execution_mode", "ACTUAL_NATIVE_NO_TOOLS_PG_DOCKER_GIT")
    record_property("approval_actor", "SCRIPTED_SYNTHETIC_TEST_OWNER_NOT_HUMAN_ACCEPTANCE")
    record_property("prompt_sha256", PROMPT_SHA256)
    record_property("native_binary_sha256", PINNED_BINARY_SHA256)
    record_property("source_commit", _git(ROOT, "rev-parse", "HEAD"))
    demo = ProposalDemo(tmp_path / "native-build", r1_database, adapter)
    try:
        demo.initialize()
        qualification = demo.qualify()
        record_property("qualification_status", qualification["status"])
        record_property("qualification_reason", qualification.get("reason", ""))
        assert qualification["status"] == "PASS", qualification
        ready = demo.readiness()
        assert ready["ready"], ready
        certificate, policy = str(ready["certificate_sha256"]), str(ready["policy_sha256"])
        base = _git(demo.bare, "rev-parse", "refs/heads/main")
        goal = str(uuid4())
        assert demo.start(goal, certificate, policy)
        deadline = time.monotonic() + 120
        while demo._jobs[goal].is_alive():
            assert time.monotonic() < deadline, "controller deadline"
            time.sleep(0.05)
        state = demo.view(goal)
        record_property("task_state_before_approval", state["goal"]["state"])
        assert state["goal"]["state"] == "WAITING_APPROVAL", state
        evidence = state["evidence"]
        assert evidence and evidence["checks"]
        assert all(check["verdict"] == "PASS" for check in evidence["checks"])
        assert _git(demo.bare, "rev-parse", "refs/heads/main") == base
        approval = state["approval"]
        assert approval
        with pytest.raises(KernelDenied, match="digest_mismatch"):
            demo.decide(goal, approval["id"], "ff" * 32, approval["version"], "approve", str(uuid4()))
        assert _git(demo.bare, "rev-parse", "refs/heads/main") == base
        with demo.connect() as connection:
            assert not connection.execute(
                "SELECT 1 FROM panestria.side_effect WHERE task_id=%s", (state["goal"]["task_id"],)
            ).fetchall()
        # This exact decision is test input, not an actual owner's release signoff.
        demo.decide(goal, approval["id"], approval["effect_digest"], approval["version"], "approve", str(uuid4()))
        assert demo.view(goal)["goal"]["status"] == "COMPLETED"
        merged = _git(demo.bare, "rev-parse", "refs/heads/main")
        assert merged == evidence["candidate_commit"] and merged != base
        with demo.connect() as connection:
            assert connection.execute(
                "SELECT state FROM panestria.worker_invocation WHERE task_id=%s", (state["goal"]["task_id"],)
            ).fetchall() == [("RETURNED",), ("RETURNED",)]
            assert connection.execute(
                "SELECT state FROM panestria.side_effect WHERE task_id=%s", (state["goal"]["task_id"],)
            ).fetchall() == [("SUCCEEDED",)]
        assert len(adapter.observations) == 2
        assert all(status == "CANDIDATE" and not accepted for status, accepted, _ in adapter.observations)
        demo.close()
        restarted = ProposalDemo(demo.root, r1_database, adapter)
        try:
            restarted.initialize()
            restarted.recover()
            assert restarted.view(goal)["goal"]["status"] == "COMPLETED"
            assert not restarted.start(goal, certificate, policy)
            assert len(adapter.observations) == 2
            assert _git(restarted.bare, "rev-parse", "refs/heads/main") == merged
        finally:
            restarted.close()
        record_property("native_call_count", len(adapter.observations))
        record_property("stdout_sha256", ",".join(observation[2] for observation in adapter.observations))
        record_property("independent_evidence_sha256", evidence["sha256"])
        record_property("protected_merge", "EXACT_TEST_APPROVAL_ONE_SUCCEEDED_EFFECT_NO_REPLAY")
    finally:
        demo.close()
