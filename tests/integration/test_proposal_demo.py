"""Actual Postgres + Docker + protected Git; provider fixtures are NOT live Claude proof."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from panestria.api.proposal_demo import create_demo_app
from panestria.brokers.harness.claude_proposal import ClaudeProposalAdapter, ProposalReceipt
from panestria.brokers.harness.process_runner import ProcessReceipt
from panestria.contracts.native_proposal import CodeProposal
from panestria.contracts.policy import TrustAxis
from panestria.execution.proposal_certificate import ACTIONS
from panestria.execution.proposal_demo import DemoUnavailable, ProposalDemo, _git
from panestria.kernel.errors import KernelDenied
from panestria.kernel.sessions import SessionService
from panestria.kernel.uow import UnitOfWork
from panestria.policy.profiles import CertificateRejected, CertificateStore


class ProviderFixture(ClaudeProposalAdapter):
    """Test seam only; the production CLI has no fixture/provider switch."""

    def __init__(self) -> None:
        self.calls = 0
        self.content = "def add(a, b):\n    return a + b\n"
        self.reason = ""
        self.block = False
        self.started = threading.Event()

    def propose(self, *, wall_seconds: float = 90, cancel: threading.Event | None = None) -> ProposalReceipt:
        self.calls += 1
        self.started.set()
        if self.block:
            assert cancel is not None
            assert cancel.wait(15)
            return ProposalReceipt(
                "CANCELLED",
                "cancelled",
                None,
                ProcessReceipt("CANCELLED", True, -15, "cancelled", "ab" * 32, "cd" * 32, None),
            )
        status = "UNAVAILABLE" if self.reason else "CANDIDATE"
        proposal = None if self.reason else CodeProposal(path="calculator.py", content=self.content)
        return ProposalReceipt(
            status,
            self.reason or "synthetic_fixture",
            proposal,
            ProcessReceipt(status, False, 0, "synthetic_fixture", "ab" * 32, "cd" * 32, None),
        )


@pytest.fixture
def demo(r1_database: str, tmp_path: Path) -> ProposalDemo:
    result = ProposalDemo(tmp_path / "demo", r1_database, ProviderFixture())
    result.initialize()
    yield result
    result.close()


def qualify(demo: ProposalDemo) -> dict[str, object]:
    # Native transport is a labeled fixture. Application and verification are
    # real Docker runs. Attestations exist only in this disposable test root.
    result = demo.qualify()
    assert result["status"] == "PASS", result
    ready = demo.readiness()
    assert ready["ready"], ready
    return ready


def run(demo: ProposalDemo) -> tuple[str, dict[str, object]]:
    ready = qualify(demo)
    goal = str(uuid4())
    assert demo.start(goal, str(ready["certificate_sha256"]), str(ready["policy_sha256"]))
    wait(demo, goal)
    return goal, demo.view(goal)


def wait(demo: ProposalDemo, goal: str) -> None:
    deadline = time.monotonic() + 60
    while demo._jobs[goal].is_alive():
        if time.monotonic() > deadline:
            raise AssertionError("controller deadline")
        time.sleep(0.05)


def test_full_flow_needs_exact_owner_approval_and_only_then_merges(demo: ProposalDemo) -> None:
    goal, state = run(demo)
    assert state["goal"]["state"] == "WAITING_APPROVAL", state
    assert all(check["verdict"] == "PASS" for check in state["evidence"]["checks"])
    assert "return a + b" in state["diff"]
    assert "return a - b" in _git(demo.bare, "show", "refs/heads/main:calculator.py")
    assert demo.adapter.calls == 2  # operator compatibility probe, then one task
    approval = state["approval"]
    with pytest.raises(KernelDenied, match="digest_mismatch"):
        demo.decide(goal, approval["id"], "ff" * 32, approval["version"], "approve", str(uuid4()))
    assert "return a - b" in _git(demo.bare, "show", "refs/heads/main:calculator.py")
    demo.decide(goal, approval["id"], approval["effect_digest"], approval["version"], "approve", str(uuid4()))
    assert demo.view(goal)["goal"]["status"] == "COMPLETED"
    assert "return a + b" in _git(demo.bare, "show", "refs/heads/main:calculator.py")
    with demo.connect() as c:
        assert c.execute(
            "SELECT state FROM panestria.worker_invocation WHERE task_id=%s", (state["goal"]["task_id"],)
        ).fetchall() == [("RETURNED",), ("RETURNED",)]
        assert c.execute(
            "SELECT state FROM panestria.side_effect WHERE task_id=%s", (state["goal"]["task_id"],)
        ).fetchall() == [("SUCCEEDED",)]


def test_bad_candidate_fails_independent_tests_and_never_requests_merge(demo: ProposalDemo) -> None:
    ready = qualify(demo)
    demo.adapter.content = "def add(a, b):\n    return a - b + 0\n"
    goal = str(uuid4())
    demo.start(goal, str(ready["certificate_sha256"]), str(ready["policy_sha256"]))
    wait(demo, goal)
    state = demo.view(goal)
    assert state["goal"]["status"] == "FAILED", state
    assert state["approval"] is None
    assert state["evidence"]["checks"][0]["verdict"] == "FAIL"
    assert "return a - b" in _git(demo.bare, "show", "refs/heads/main:calculator.py")


def test_unavailable_qualification_has_no_certificate_or_task(demo: ProposalDemo) -> None:
    demo.adapter.reason = "quota_unavailable"
    assert demo.qualify() == {"status": "UNAVAILABLE", "reason": "quota_unavailable"}
    assert not (demo.root / "certificate.json").exists()
    assert demo.view()["goal"] is None
    with pytest.raises(DemoUnavailable):
        demo.start(str(uuid4()), "ff" * 32, "ff" * 32)
    assert demo.adapter.calls == 1


def test_attestation_is_demo_only_and_changed_runtime_is_denied(
    demo: ProposalDemo, monkeypatch: pytest.MonkeyPatch
) -> None:
    ready = qualify(demo)
    trust = TrustAxis(
        version=1,
        profile="PERSONAL_SANDBOX",
        allowed_actions=ACTIONS,
        runtime_certificate_sha256=str(ready["certificate_sha256"]),
    )
    with pytest.raises(CertificateRejected):
        CertificateStore(demo.certificates.root, demo.certificates.runtime_versions).validate(trust)
    monkeypatch.setattr("panestria.execution.proposal_certificate.runtime_versions", lambda: {"changed": "runtime"})
    assert not demo.readiness()["ready"]


def test_cancel_stops_provider_and_restart_never_replays_it(demo: ProposalDemo) -> None:
    ready = qualify(demo)
    demo.adapter.block = True
    demo.adapter.started.clear()
    goal = str(uuid4())
    demo.start(goal, str(ready["certificate_sha256"]), str(ready["policy_sha256"]))
    assert demo.adapter.started.wait(15)
    state = demo.view(goal)
    demo.cancel(goal, state["goal"]["version"])
    wait(demo, goal)
    assert demo.view(goal)["goal"]["status"] == "CANCELLED"
    calls = demo.adapter.calls
    demo.recover()
    assert not demo.start(goal, str(ready["certificate_sha256"]), str(ready["policy_sha256"]))
    assert demo.adapter.calls == calls


def test_browser_requires_pairing_exact_origin_csrf_and_valid_session(demo: ProposalDemo) -> None:
    origin = "http://127.0.0.1:18871"
    with TestClient(create_demo_app(demo, origin), base_url=origin) as client:
        assert client.get("/").status_code == 200
        assert client.get("/demo.js").status_code == 200
        assert client.get("/v1/demo").status_code == 403
        assert client.post("/v1/session/code", json={}).status_code == 404
        assert client.post("/v1/session/pair", json={"code": "00000000"}).status_code == 403
        service = SessionService(bytes.fromhex(demo.identity["session_secret"]))
        with demo.connect() as c:
            code = service.issue_pairing_code(UnitOfWork(c), demo.actor, ttl_seconds=300)
        paired = client.post("/v1/session/pair", json={"code": code}, headers={"origin": origin})
        assert paired.status_code == 200, paired.text
        csrf = paired.json()["csrf_token"]
        assert "HttpOnly" in paired.headers["set-cookie"]
        assert client.get("/v1/demo").status_code == 200
        body = {"goal_id": str(uuid4()), "certificate_sha256": "ff" * 32, "policy_sha256": "ff" * 32}
        assert client.post("/v1/demo/start", json=body, headers={"origin": origin}).status_code == 403
        assert (
            client.post(
                "/v1/demo/start", json=body, headers={"origin": "https://evil.invalid", "x-panestria-csrf": csrf}
            ).status_code
            == 403
        )
        assert (
            client.post("/v1/demo/start", json=body, headers={"origin": origin, "x-panestria-csrf": csrf}).status_code
            == 409
        )
        assert (
            client.post("/v1/session/logout", json={}, headers={"origin": origin, "x-panestria-csrf": csrf}).status_code
            == 200
        )
        assert client.get("/v1/demo").status_code == 403
    assert demo.adapter.calls == 0


def test_rejected_merge_and_restarted_review_never_merge_implicitly(demo: ProposalDemo) -> None:
    goal, state = run(demo)
    restarted = ProposalDemo(demo.root, demo.dsn, demo.adapter)
    restarted.initialize()
    restarted.recover()
    assert restarted.view(goal)["goal"]["state"] == "WAITING_APPROVAL"
    assert restarted.adapter.calls == 2
    approval = state["approval"]
    restarted.decide(goal, approval["id"], approval["effect_digest"], approval["version"], "deny", str(uuid4()))
    assert restarted.view(goal)["goal"]["status"] == "FAILED"
    assert "return a - b" in _git(demo.bare, "show", "refs/heads/main:calculator.py")
    with demo.connect() as c:
        assert (
            c.execute("SELECT 1 FROM panestria.side_effect WHERE task_id=%s", (state["goal"]["task_id"],)).fetchone()
            is None
        )


def test_task_quota_rejection_is_recorded_once_without_apply_or_fallback(demo: ProposalDemo) -> None:
    ready = qualify(demo)
    demo.adapter.reason = "quota_unavailable"
    goal = str(uuid4())
    demo.start(goal, str(ready["certificate_sha256"]), str(ready["policy_sha256"]))
    wait(demo, goal)
    state = demo.view(goal)
    assert state["goal"]["status"] == "FAILED"
    assert state["events"][-1]["payload"]["reason"] == "quota_unavailable"
    assert state["approval"] is None and state["evidence"] is None
    demo.recover()
    assert not demo.start(goal, str(ready["certificate_sha256"]), str(ready["policy_sha256"]))
    assert demo.adapter.calls == 2
    with demo.connect() as c:
        assert c.execute(
            "SELECT invocation_key,state FROM panestria.worker_invocation WHERE task_id=%s", (state["goal"]["task_id"],)
        ).fetchall() == [("native-proposal", "RETURNED")]


def test_unknown_qualification_never_retries_after_restart(demo: ProposalDemo) -> None:
    (demo.root / "qualification.json").write_text(json.dumps({"status": "STARTED"}))
    with pytest.raises(DemoUnavailable, match="outcome_unknown"):
        demo.qualify()
    assert demo.adapter.calls == 0
    assert not demo.readiness()["ready"]


def test_restart_interrupts_claimed_native_call_without_replay(
    demo: ProposalDemo, monkeypatch: pytest.MonkeyPatch
) -> None:
    ready = qualify(demo)

    def ambiguous(**kwargs: object) -> ProposalReceipt:
        demo.adapter.calls += 1
        raise RuntimeError("synthetic transport interruption")

    monkeypatch.setattr(demo.adapter, "propose", ambiguous)
    goal = str(uuid4())
    demo.start(goal, str(ready["certificate_sha256"]), str(ready["policy_sha256"]))
    wait(demo, goal)
    state = demo.view(goal)
    assert state["goal"]["status"] == "FAILED"
    with demo.connect() as c:
        assert c.execute(
            "SELECT state FROM panestria.worker_invocation WHERE task_id=%s", (state["goal"]["task_id"],)
        ).fetchall() == [("UNKNOWN",)]
    demo.recover()
    assert not demo.start(goal, str(ready["certificate_sha256"]), str(ready["policy_sha256"]))
    assert demo.adapter.calls == 2


def test_commit_time_authorization_denial_prevents_task_admission(demo: ProposalDemo) -> None:
    ready = qualify(demo)
    goal = str(uuid4())

    def denied(connection: psycopg.Connection) -> None:
        raise KernelDenied("unauthorized")

    with pytest.raises(KernelDenied, match="unauthorized"):
        demo.start(goal, str(ready["certificate_sha256"]), str(ready["policy_sha256"]), authorize=denied)
    assert demo.adapter.calls == 1
    assert demo.view()["goal"] is None


def test_lost_merge_receipt_reconciles_actual_git_without_another_worker(
    demo: ProposalDemo, monkeypatch: pytest.MonkeyPatch
) -> None:
    from panestria.execution.outbox import EffectExecutor
    from panestria.kernel.effects import SideEffectService

    goal, state = run(demo)

    def lost_receipt(executor: EffectExecutor, actor: object, effect_id: str) -> None:
        service = SideEffectService()
        with executor._connect() as c:
            claim = service.claim(UnitOfWork(c), actor, effect_id)
        executor._target.dispatch(claim)  # Real protected Git CAS succeeds.
        with executor._connect() as c:
            service.finish(UnitOfWork(c), actor, claim, None)

    monkeypatch.setattr(EffectExecutor, "dispatch", lost_receipt)
    approval = state["approval"]
    with pytest.raises(KernelDenied, match="merge_not_confirmed"):
        demo.decide(goal, approval["id"], approval["effect_digest"], approval["version"], "approve", str(uuid4()))
    assert "return a + b" in _git(demo.bare, "show", "refs/heads/main:calculator.py")
    demo.recover()
    assert demo.view(goal)["goal"]["status"] != "COMPLETED"
    demo.reconcile(goal)
    assert demo.view(goal)["goal"]["status"] == "COMPLETED"
    assert demo.adapter.calls == 2


def test_cancellation_goal_lock_allows_a_worker_to_record_its_final_event(r1_task: dict[str, str]) -> None:
    from panestria.kernel.cancellation import CancellationService
    from panestria.kernel.goals import Actor
    from panestria.kernel.repositories.tasks import append_event

    actor = Actor(r1_task["owner"], r1_task["project"])
    errors: list[Exception] = []
    ready = threading.Event()
    cancel_pid: list[int] = []
    with psycopg.connect(r1_task["dsn"]) as worker:
        worker.execute("SET LOCAL statement_timeout='1500ms'")
        worker.execute("SELECT id FROM panestria.task WHERE id=%s FOR UPDATE", (r1_task["task"],))
        worker_pid = worker.info.backend_pid

        def cancel() -> None:
            try:
                with psycopg.connect(r1_task["dsn"]) as c:
                    cancel_pid.append(c.info.backend_pid)
                    ready.set()
                    CancellationService().cancel(
                        UnitOfWork(c), actor, r1_task["goal"], 0, "synthetic cancel race", correlation_id=str(uuid4())
                    )
            except Exception as exc:
                errors.append(exc)

        thread = threading.Thread(target=cancel)
        thread.start()
        assert ready.wait(2)
        deadline = time.monotonic() + 3
        with psycopg.connect(r1_task["dsn"], autocommit=True) as observer:
            while worker_pid not in observer.execute("SELECT pg_blocking_pids(%s)", (cancel_pid[0],)).fetchone()[0]:
                assert time.monotonic() < deadline, "cancel did not reach task lock"
                time.sleep(0.01)
        # Cancellation holds the goal lock and waits for this task. The worker
        # must be able to insert a goal FK without waiting on that goal lock.
        append_event(
            UnitOfWork(worker),
            goal_id=r1_task["goal"],
            task_id=r1_task["task"],
            actor=actor.owner_id,
            kind="fixture.worker_returned",
            payload={},
        )
    thread.join(timeout=5)
    assert not thread.is_alive() and not errors, errors
    with psycopg.connect(r1_task["dsn"]) as c:
        assert c.execute("SELECT status FROM panestria.goal WHERE id=%s", (r1_task["goal"],)).fetchone() == (
            "CANCELLED",
        )
