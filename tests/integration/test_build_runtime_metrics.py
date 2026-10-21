"""Actual canonical/CLI/storage timing capture; native/auth/capacity are fixtures."""

import json
import stat
from concurrent.futures import ThreadPoolExecutor

from test_native_plan_execution import native_plan as native_plan  # noqa: F401
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401
from test_owner_build_cli import invoke

from panestria.telemetry.performance import latest_snapshot


def enable(owner, f):
    cfg = json.loads(f.config.read_text())
    cfg["record_runtime_metrics"] = True
    f.config.write_text(json.dumps(cfg))
    owner.settings = owner.settings.model_copy(update={"record_runtime_metrics": True})


def test_actual_finished_build_capture_deduplicates_sources_and_full_history_does_not_change_outcome(
    native_plan, prepared_plan
):
    f, owner, _, plan = prepared_plan
    _, runner, _, state = native_plan
    assert owner.settings.record_runtime_metrics is False and not (f.root / "metrics").exists()
    enable(owner, f)
    result = runner.run(plan.plan_id, public_subscription_run=True)
    assert result["status"] == "WAITING_APPROVAL" and result["metrics"]["status"] == "SAVED"
    directory = f.root / "metrics"
    snapshot = latest_snapshot(directory)
    observations = {m.metric: m for m in snapshot.observations if m.scope == "runtime_build"}
    assert observations["runtime.receipt_present_fraction"].value == 1.0
    assert observations["runtime.receipt_present_fraction"].samples == 5
    assert observations["verification.required_pass_fraction"].value == 1.0
    assert observations["quality.correct_fraction"].value is observations["cost.actual"].value is None
    timings = [m for m in snapshot.observations if m.metric.startswith("latency.")]
    assert len(timings) == 6 and all(m.value is not None and m.value > 0 for m in timings)
    assert sorted(m.samples for m in timings) == [1, 1, 2, 2, 2, 2]
    assert all(m.model is m.source_commit is None for m in snapshot.observations)
    raw = (directory / "sources" / result["metrics"]["source_sha256"]).read_bytes()
    retained = json.loads(raw)
    assert retained["qualification"] == "NOT_ASSESSED" and len(retained["records"]) == 5
    assert b"bounded Bash build" not in raw and b"value = 43" not in raw and f.dsn.encode() not in raw
    with owner.connect() as c:
        before = c.execute("SELECT count(*) FROM panestria.task_event").fetchone()
        originals = c.execute(
            "SELECT i.id::text,extract(epoch FROM(i.finished_at-i.created_at)) FROM panestria.worker_invocation i "
            "JOIN panestria.task t ON t.id=i.task_id WHERE t.goal_id=%s",
            (plan.goal_id,),
        ).fetchall()
    assert {r["invocation_id"]: r["intent_to_return_seconds"] for r in retained["records"]} == {
        key: float(seconds) for key, seconds in originals
    }
    second = invoke(f, "metrics", plan.goal_id)
    assert second["status"] == "SAVED" and second["source_sha256"] == result["metrics"]["source_sha256"]
    assert second["snapshot"] != result["metrics"]["snapshot"]
    assert len(list((directory / "sources").iterdir())) == 1
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in directory.glob("*.json"))
    # A sparse fixture accounts for history pressure without writing 16 MiB.
    with (directory / "budget-fixture.bin").open("wb") as stream:
        stream.truncate(16 * 1024 * 1024)
    blocked = runner.run(plan.plan_id, public_subscription_run=True)
    assert blocked["status"] == "WAIT" and blocked["metrics"]["status"] == "UNAVAILABLE"
    assert state["launches"] == 2 and owner.status(plan.goal_id)["task_state"] == "WAITING_APPROVAL"
    assert len(list((directory / "sources").iterdir())) == 1
    assert len(list(directory.glob("*.json"))) == 2
    with owner.connect() as c:
        assert c.execute("SELECT count(*) FROM panestria.task_event").fetchone() == before


def test_actual_unknown_invocations_are_not_counted_as_returned_latency(native_plan, prepared_plan):
    f, owner, _, plan = prepared_plan
    _, runner, _, state = native_plan
    enable(owner, f)
    state["block"] = True
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(runner.run, plan.plan_id, public_subscription_run=True)
        assert state["started"].wait(10)
        before = owner.status(plan.goal_id)
        owner.cancel(plan.goal_id, before["row_version"])
        result = future.result(timeout=15)
    assert result["status"] == "STOPPED" and result["metrics"]["status"] == "SAVED"
    snapshot = latest_snapshot(f.root / "metrics")
    for m in snapshot.observations:
        if m.metric.startswith("latency.") or m.metric == "verification.required_pass_fraction":
            assert m.value is None and m.samples == 0 and m.reason == "UNMEASURED"
    raw = json.loads((f.root / "metrics/sources" / result["metrics"]["source_sha256"]).read_bytes())
    assert len(raw["records"]) == 2 and all(r["state"] == "UNKNOWN" for r in raw["records"])
    with owner.connect() as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.build_active_worker_claim WHERE plan_id=%s", (plan.plan_id,)
        ).fetchone() == (2,)
