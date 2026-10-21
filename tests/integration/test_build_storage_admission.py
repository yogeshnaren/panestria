"""Actual disk/PG/CLI/Build flow; native generation/auth/capacity are fixtures."""

import json
import threading

import pytest
from test_native_plan_execution import native_plan as native_plan  # noqa: F401
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401
from test_owner_build_cli import invoke
from test_owner_build_cli import owner_cli as owner_cli  # noqa: F401
from test_registered_check_authority import git
from typer.testing import CliRunner

from panestria.cli.main import app
from panestria.execution.build_storage import build_storage_admission
from panestria.kernel.errors import KernelDenied


def configure(f, owner, *, reserve=0):
    path = f.config.parent / "storage.json"
    policy = {
        "notifications_enabled": True,
        "filesystem": str(f.root),
        "warning_percent": 1,
        "critical_percent": 100,
        "minimum_free_bytes": reserve,
        "include_docker": True,
        "include_timeshift": True,
        "components": [{"label": "must_not_scan", "path": "/DO_NOT_SCAN_SENTINEL"}],
    }
    path.write_text(json.dumps(policy))
    path.chmod(0o600)
    cfg = json.loads(f.config.read_text())
    cfg.update(storage_policy=str(path), anticipated_build_write_bytes=1024**2)
    f.config.write_text(json.dumps(cfg))
    owner.settings = owner.settings.model_copy(
        update={"storage_policy": path, "anticipated_build_write_bytes": 1024**2}
    )
    return path, policy


def event_count(owner):
    with owner.connect() as c:
        return c.execute("SELECT count(*) FROM panestria.task_event").fetchone()


def test_actual_reserve_pressure_defers_inventory_and_claims_without_mutation(native_plan, prepared_plan):
    f, owner, _, plan = prepared_plan
    _, runner, _, state = native_plan
    path, policy = configure(f, owner, reserve=2**63 - 1)
    notices = []
    runner.on_storage_observation = notices.append
    before = event_count(owner)
    existing = list((f.root / "plan-inventory").iterdir())
    preview = invoke(f, "storage-preview")
    assert preview["decision"] == "DEFER" and preview["reason"] == "storage_reserve_at_risk"
    assert preview["report"]["capacity"]["status"] == "OBSERVED"
    assert preview["report"]["components"] == [] and preview["report"]["timeshift"] == {"status": "NOT_REQUESTED"}
    with pytest.raises(KernelDenied, match="storage_reserve_at_risk"):
        runner.inventory(f.base)
    stopped = runner.run(plan.plan_id, public_subscription_run=True)
    assert stopped["status"] == "WAIT" and stopped["reason"] == "storage_admission_deferred"
    assert state["launches"] == 0 and len(notices) == 1  # unchanged warnings do not spam
    cli = CliRunner().invoke(app, ["plan", "run", "--config", str(f.config), plan.plan_id, "--public-subscription-run"])
    assert cli.exit_code == 0 and json.loads(cli.stdout)["reason"] == "storage_admission_deferred"
    assert json.loads(cli.stderr)["notification"] == "build_storage_admission"
    assert f.dsn not in cli.stderr
    assert notices[0]["cleanup_authority"] == "NONE"
    assert all("CREATED" == t["task_state"] for t in stopped["tasks"])
    assert event_count(owner) == before and list((f.root / "plan-inventory").iterdir()) == existing
    assert git(f.bare, "rev-parse", "HEAD") == f.base
    with owner.connect() as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.build_worker_claim WHERE plan_id=%s", (plan.plan_id,)
        ).fetchone() == (0,)
    path.chmod(0o644)
    assert build_storage_admission(owner.settings)["reason"] == "storage_policy_unconfirmed"
    path.chmod(0o600)
    policy["filesystem"] = str(path.parent / "nonexistent-filesystem")
    path.write_text(json.dumps(policy))
    assert build_storage_admission(owner.settings)["reason"] == "storage_capacity_unknown"
    policy["notifications_enabled"] = False
    path.write_text(json.dumps(policy))
    assert invoke(f, "storage-preview")["status"] == "NOT_ENABLED"
    assert state["launches"] == 0 and event_count(owner) == before


def test_actual_pressure_after_workers_defers_only_new_final_work_then_explicit_resume_uses_handoffs(
    native_plan, prepared_plan, monkeypatch
):
    f, owner, _, plan = prepared_plan
    _, runner, _, state = native_plan
    path, policy = configure(f, owner)
    # Both separately enabled observers coexist; metric capture is derived
    # metadata, not another worker or a reason to ignore storage deferral.
    owner.settings = owner.settings.model_copy(update={"record_runtime_metrics": True})
    notices, lock = [], threading.Lock()
    runner.on_storage_observation = notices.append
    original = runner._one

    def pressure_before_return(*args):
        result = original(*args)  # Actual scoped MCP/Docker/checks and canonical handoff.
        with lock:
            path.write_text(json.dumps({**policy, "minimum_free_bytes": 2**63 - 1}))
        return result

    monkeypatch.setattr(runner, "_one", pressure_before_return)
    stopped = runner.run(plan.plan_id, public_subscription_run=True)
    assert stopped["status"] == "WAIT" and stopped["storage_admission"]["decision"] == "DEFER"
    assert stopped["metrics"]["status"] == "SAVED"
    assert state["launches"] == state["peak"] == 2
    assert [n["decision"] for n in notices] == ["ALLOW", "DEFER"]
    assert all(r["status"] == "NODE_VERIFIED" for r in stopped["worker_observations"])
    with owner.connect() as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.task_attempt WHERE task_id=%s", (plan.nodes[-1].task_id,)
        ).fetchone() == (0,)
        assert c.execute(
            "SELECT count(*) FROM panestria.build_handoff WHERE plan_id=%s", (plan.plan_id,)
        ).fetchone() == (2,)
    # Only explicit owner re-invocation after capacity policy becomes eligible.
    path.write_text(json.dumps(policy))
    resumed = runner.run(plan.plan_id, public_subscription_run=True)
    assert resumed["status"] == "WAITING_APPROVAL" and resumed["storage_admission"]["decision"] == "ALLOW"
    assert resumed["metrics"]["status"] == "SAVED"
    assert state["launches"] == 2 and git(f.bare, "rev-parse", "HEAD") == f.base
    assert [n["decision"] for n in notices] == ["ALLOW", "DEFER", "ALLOW"]
