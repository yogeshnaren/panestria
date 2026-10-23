"""Real PG/Git/Docker two-worker control flow; native/auth/capacity are explicit fixtures.

This is NOT live Claude/OS/vendor qualification or a release-gate pass. The fake
transport drives the actual MCP/gateway and independent verification boundaries.
"""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest
from test_owner_build_cli import contract, invoke, prepare
from test_owner_build_cli import owner_cli as owner_cli  # noqa: F401
from test_registered_check_authority import git

from panestria.brokers.harness.claude_build import PROFILE, ClaudeScopedBashAdapter
from panestria.brokers.harness.claude_check import CheckProfileObservation
from panestria.brokers.harness.claude_proposal import ClaudeProposalAdapter
from panestria.brokers.harness.event_parser import NativeResult
from panestria.brokers.harness.process_runner import ProcessReceipt
from panestria.config_build import load_build_settings
from panestria.contracts.goal import contract_sha256, load_contract
from panestria.contracts.hardware import HardwareManifest
from panestria.contracts.plan import PlanNode, PlanProposal
from panestria.execution.native_plan import NativePlanRunner
from panestria.execution.owner_build import OwnerBuild
from panestria.kernel.errors import KernelDenied
from panestria.kernel.plan_store import PlanStore
from panestria.kernel.plan_submission import PlanSubmissionService
from panestria.kernel.uow import UnitOfWork
from panestria.resources.hardware import PROBE_SHA256, HardwareProbe


@pytest.fixture
def prepared_plan(owner_cli, r1_migration_task, monkeypatch, request):
    f = owner_cli
    f.dsn = r1_migration_task["dsn"]
    monkeypatch.setenv("PANESTRIA_DATABASE_URL", f.dsn)
    ref = prepare(f)
    owner = OwnerBuild(load_build_settings(f.config), f.dsn)
    runner = NativePlanRunner(owner)
    inventory = runner.inventory(f.base)
    document = contract(f, ref)
    document["constraints"]["permitted_capabilities"].append("trusted-test-runner")
    document["budget"]["max_wall_seconds"] = getattr(request, "param", {}).get("wall_seconds", 270)
    document["non_goals"] = getattr(request, "param", {}).get("non_goals", [])
    goal = load_contract(document)
    ids = [str(uuid4()) for _ in range(3)]
    nodes = tuple(
        PlanNode(
            task_id=key,
            depends_on=tuple(ids[:2]) if i == 2 else (),
            worker_ref="trusted-integrator" if i == 2 else "claude-public-bash",
            capabilities=("trusted-test-runner",) if i == 2 else ("scoped-bash",),
            paths=("calculator.py", "notes/build.txt")
            if i == 2
            else (("calculator.py",) if i == 0 else ("notes/build.txt",)),
            acceptance_keys=tuple(c.id for c in goal.acceptance) if i == 2 else ("paths",),
            expected_artifacts=("patch",),
            attempts=1,
            wall_seconds_per_attempt=90,
            api_microusd_per_attempt=0,
        )
        for i, key in enumerate(ids)
    )
    proposal = PlanProposal(
        plan_id=str(uuid4()),
        owner_id=owner.actor.owner_id,
        project_id=owner.actor.project_id,
        goal_id=goal.goal_id,
        contract_sha256=contract_sha256(goal),
        inventory_sha256=inventory.sha256(),
        privacy_class="PUBLIC",
        nodes=nodes,
    )
    with owner.connect() as c:
        staged = PlanSubmissionService().stage(UnitOfWork(c), owner.actor, document, proposal, inventory, "native-plan")
    with owner.connect() as c:
        PlanStore().accept(UnitOfWork(c), owner.actor, proposal.plan_id, staged.effect_digest, accept_plan=True)
    return f, owner, runner, proposal


@pytest.fixture
def native_plan(prepared_plan, monkeypatch):
    _f, owner, runner, proposal = prepared_plan
    state = {
        "launches": 0,
        "active": 0,
        "peak": 0,
        "contexts": [],
        "metadata": 0,
        "block": False,
        "unavailable": False,
        "started": threading.Event(),
        "lock": threading.Lock(),
        "barrier": threading.Barrier(2),
    }

    def inspect(_self):
        state["metadata"] += 1  # Explicit nonlive supported-metadata fixture; no credentials read.

    monkeypatch.setattr(ClaudeProposalAdapter, "inspect", inspect)

    def capacity(_self):
        return HardwareManifest(
            observed_at=datetime.now(UTC),
            simulated=False,
            os="Linux",
            arch="fixture",
            kernel="fixture",
            cpu="fixture",
            logical_cores=8,
            ram_available_gib=16.0,
            disk_free_gib=20.0,
            accelerators=(),
            on_ac_power=True,
            gpu_status="NOT_PROBED_CPU_ONLY",
            probe_sha256=PROBE_SHA256,
            catalog_version="TEST_FIXTURE_NOT_LIVE",
        )

    monkeypatch.setattr(HardwareProbe, "collect_cpu", capacity)

    def native(_self, session, *, public_context, cancel=None, startup_only=False, before_launch=None):
        assert before_launch is not None
        before_launch()
        context = json.loads(public_context)
        with state["lock"]:
            state["contexts"].append(context)
            state["launches"] += 1
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
            if state["active"] == 2:
                state["started"].set()
        try:
            if state["block"]:
                assert cancel is not None and cancel.wait(10)
            elif not state["unavailable"]:
                if state.get("expected_workers", 2) > 1:
                    state["barrier"].wait(timeout=10)
                paths = context["assignment"]["paths"]
                assert paths and set(paths) <= {"calculator.py", "notes/build.txt"}
                commands = []
                if "calculator.py" in paths:
                    commands.append("printf 'value = 43\\n' > calculator.py")
                if "notes/build.txt" in paths:
                    commands.append("mkdir -p notes; printf 'bounded Bash build\\n' > notes/build.txt")
                script = "; ".join(commands)
                for body in (
                    {
                        "jsonrpc": "2.0",
                        "id": "init",
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-06-18",
                            "capabilities": {},
                            "clientInfo": {"name": "TEST_FIXTURE_NOT_LIVE", "version": "1"},
                        },
                    },
                    {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                    {
                        "jsonrpc": "2.0",
                        "id": "edit",
                        "method": "tools/call",
                        "params": {
                            "name": "run_scoped_bash",
                            "arguments": {"job_ref": session.references[1], "script": script},
                        },
                    },
                ):
                    response = session.handle(json.dumps(body).encode())
                assert json.loads(response)["result"]["isError"] is False
        finally:
            with state["lock"]:
                state["active"] -= 1
        unavailable = state["unavailable"]
        return CheckProfileObservation(
            ProcessReceipt(
                "UNAVAILABLE" if unavailable else "CANDIDATE",
                True,
                0,
                "quota_unavailable" if unavailable else "TEST_FIXTURE_NOT_LIVE",
                "ab" * 32,
                "cd" * 32,
                NativeResult("CANDIDATE", False, "TEST_FIXTURE_NOT_LIVE", "ab" * 32, _self.native_model)
                if _self.native_model is not None
                else None,
            ),
            True,
            True,
            "ef" * 32,
            profile=PROFILE,
            requested_model=_self.native_model,
        )

    monkeypatch.setattr(ClaudeScopedBashAdapter, "build_public", native)
    return owner, runner, proposal, state


def test_two_scoped_workers_and_create_only_node_reach_exact_owner_review(native_plan, record_property):
    owner, runner, plan, state = native_plan
    result = runner.run(plan.plan_id, public_subscription_run=True)
    record_property("native_plan_result", json.dumps(result, sort_keys=True))
    assert result["status"] == "WAITING_APPROVAL", result
    assert state["launches"] == 2 and state["peak"] == 2
    assert any(not context["files"] for context in state["contexts"])  # New file has no invented source contents.
    assert {tuple(c["assignment"]["paths"]) for c in state["contexts"]} == {("calculator.py",), ("notes/build.txt",)}
    review = owner.status(plan.goal_id, diff=True)
    assert review["task_state"] == "WAITING_APPROVAL" and "notes/build.txt" in review["diff"]
    assert all(c["verdict"] == "PASS" for c in review["checks"])
    with owner.connect() as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.worker_invocation i "
            "JOIN panestria.task t ON t.id=i.task_id WHERE t.goal_id=%s AND i.state='RETURNED'",
            (plan.goal_id,),
        ).fetchone() == (5,)
        assert c.execute(
            "SELECT count(*) FROM panestria.build_handoff WHERE plan_id=%s", (plan.plan_id,)
        ).fetchone() == (2,)
        assert c.execute("SELECT status FROM panestria.goal WHERE id=%s", (plan.goal_id,)).fetchone() == ("ACTIVE",)


@pytest.mark.parametrize(
    "error,code",
    [(psycopg.errors.QueryCanceled("PRIVATE_SQL_SENTINEL"), "database_statement_timeout"),
     (RuntimeError("PRIVATE_EXCEPTION_SENTINEL"), "worker_execution_unconfirmed")],
)
def test_stopped_native_worker_retains_safe_cause_and_unknown_claim(native_plan, monkeypatch, error, code):
    owner, runner, plan, state = native_plan

    def unavailable(_self, session, *, before_launch, **kwargs):
        before_launch()
        raise error

    monkeypatch.setattr(ClaudeScopedBashAdapter, "build_public", unavailable)
    result = runner.run(plan.plan_id, public_subscription_run=True)
    assert result["status"] == "STOPPED" and state["launches"] == 0
    assert result["worker_observations"] and all(r["reason"] == code for r in result["worker_observations"])
    assert "PRIVATE_" not in json.dumps(result)
    with owner.connect() as c:
        assert c.execute("SELECT count(*) FROM panestria.build_handoff WHERE plan_id=%s", (plan.plan_id,)).fetchone() == (0,)
        assert c.execute("SELECT count(*) FROM panestria.approval_request WHERE goal_id=%s", (plan.goal_id,)).fetchone() == (0,)
        assert c.execute(
            "SELECT count(*) FROM panestria.worker_invocation i JOIN panestria.task t ON t.id=i.task_id "
            "WHERE t.goal_id=%s AND i.state='UNKNOWN'", (plan.goal_id,),
        ).fetchone()[0] > 0
        assert c.execute(
            "SELECT count(*) FROM panestria.build_active_worker_claim WHERE plan_id=%s", (plan.plan_id,),
        ).fetchone()[0] > 0


def test_explicit_run_intent_and_changed_worker_declaration_refuse_before_claim(native_plan):
    owner, runner, plan, state = native_plan
    with pytest.raises(KernelDenied, match="explicit_public_build_intent_required"):
        runner.run(plan.plan_id, public_subscription_run=False)
    # A new controller build changes source/runtime identity, not permission to
    # silently choose another worker. Retain old canonical data for inspection.
    owner.certificates.runtime_versions = {}
    with pytest.raises(KernelDenied):
        runner.run(plan.plan_id, public_subscription_run=True)
    assert state["launches"] == 0
    with owner.connect() as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.build_worker_claim WHERE plan_id=%s", (plan.plan_id,)
        ).fetchone() == (0,)


def test_quota_unavailable_stops_new_admissions_without_merge_or_hidden_retry(native_plan):
    owner, runner, plan, state = native_plan
    state["unavailable"] = True
    result = runner.run(plan.plan_id, public_subscription_run=True)
    assert result["status"] == "STOPPED" and 1 <= state["launches"] <= 2
    with owner.connect() as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.approval_request WHERE goal_id=%s", (plan.goal_id,)
        ).fetchone() == (0,)
        assert c.execute(
            "SELECT count(*) FROM panestria.task_attempt WHERE task_id=%s", (plan.nodes[-1].task_id,)
        ).fetchone() == (0,)
        assert (
            c.execute(
                "SELECT count(*) FROM panestria.build_active_worker_claim WHERE plan_id=%s", (plan.plan_id,)
            ).fetchone()[0]
            >= 1
        )


def test_plan_cancel_fences_both_running_calls_and_keeps_uncertain_capacity(native_plan):
    owner, runner, plan, state = native_plan
    state["block"] = True
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(runner.run, plan.plan_id, public_subscription_run=True)
        assert state["started"].wait(10)
        before = owner.status(plan.goal_id)
        stop = owner.cancel(plan.goal_id, before["row_version"])
        assert stop["status"] == "CANCEL_REQUESTED"
        result = future.result(timeout=15)
    assert result["status"] == "STOPPED"
    with owner.connect() as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.build_evidence b "
            "JOIN panestria.task t ON t.id=b.task_id WHERE t.goal_id=%s",
            (plan.goal_id,),
        ).fetchone() == (0,)
        assert c.execute(
            "SELECT count(*) FROM panestria.approval_request WHERE goal_id=%s", (plan.goal_id,)
        ).fetchone() == (0,)
        assert c.execute(
            "SELECT count(*) FROM panestria.build_active_worker_claim WHERE plan_id=%s", (plan.plan_id,)
        ).fetchone() == (2,)


@pytest.mark.live
def test_actual_public_two_claude_plan_and_exact_final_merge(prepared_plan, record_property):
    f, owner, runner, plan = prepared_plan
    assert f.actual
    record_property(
        "scope",
        "Actual PUBLIC two-Claude fork/join and real runtime certificate; "
        "scripted test-owner approval, no human signoff",
    )
    record_property("runtime_certificate_sha256", f.cfg["certificate_sha256"])
    result = runner.run(plan.plan_id, public_subscription_run=True)
    record_property("plan_result", json.dumps(result, sort_keys=True))
    assert result["status"] == "WAITING_APPROVAL", result
    assert git(f.bare, "rev-parse", "HEAD") == f.base
    review = owner.status(plan.goal_id, diff=True)
    assert all(check["verdict"] == "PASS" for check in review["checks"])
    assert "+value = 43" in review["diff"] and "+bounded Bash build" in review["diff"]
    with owner.connect() as c:
        calls = c.execute(
            "SELECT i.id::text,i.binding->>'kind',i.state,i.receipt_sha256::text,i.finished_at::text "
            "FROM panestria.worker_invocation i JOIN panestria.task t ON t.id=i.task_id "
            "WHERE t.goal_id=%s ORDER BY i.created_at,i.id",
            (plan.goal_id,),
        ).fetchall()
        record_property("actual_invocations", json.dumps(calls))
        assert sum(call[1] == "native-proposal" for call in calls) == 2
        assert len(calls) >= 4 and all(call[2] == "RETURNED" and call[3] for call in calls)
        events = c.execute(
            "SELECT e.seq,e.kind,e.payload->>'invocation_id' FROM panestria.task_event e "
            "WHERE e.goal_id=%s AND e.kind IN ('native_build.context_disclosure','invocation.returned') "
            "ORDER BY seq",
            (plan.goal_id,),
        ).fetchall()
        record_property("invocation_order", json.dumps(events))
        native_ids = {call[0] for call in calls if call[1] == "native-proposal"}
        disclosed = [
            seq
            for seq, kind, identity in events
            if kind == "native_build.context_disclosure" and identity in native_ids
        ]
        returned = [seq for seq, kind, identity in events if kind == "invocation.returned" and identity in native_ids]
        assert len(disclosed) == len(returned) == 2 and max(disclosed) < min(returned)
        assert c.execute(
            "SELECT count(*) FROM panestria.build_handoff WHERE plan_id=%s", (plan.plan_id,)
        ).fetchone() == (2,)
    approval = review["approval"]
    args = (
        approval["approval_id"],
        approval["effect_digest"],
        str(approval["expected_version"]),
        "exact-two-worker-test-owner",
    )
    invoke(f, "approve", args[0], "ff" * 32, *args[2:], expected=1)
    assert git(f.bare, "rev-parse", "HEAD") == f.base
    merged = invoke(f, "approve", *args)
    assert merged["task_state"] == "COMPLETED"
    assert git(f.bare, "rev-parse", "HEAD") == review["candidate_commit"]
    assert git(f.source, "rev-parse", "HEAD") == f.base
    with owner.connect() as c:
        assert c.execute("SELECT status FROM panestria.goal WHERE id=%s", (plan.goal_id,)).fetchone() == ("COMPLETED",)
        assert c.execute(
            "SELECT count(*) FROM panestria.build_active_worker_claim WHERE plan_id=%s", (plan.plan_id,)
        ).fetchone() == (0,)
    record_property("native_actual_cash", "UNKNOWN_SUBSCRIPTION_ESTIMATE_ONLY_NO_DIRECT_SDK_CALL")
