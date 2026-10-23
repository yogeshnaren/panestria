"""Actual private history/CLI I/O; synthetic retained measurements, no inference."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from panestria.cli.main import app
from panestria.telemetry.ask_metrics import capture_ask_metrics
from panestria.telemetry.overview import runtime_overview, save_overview
from panestria.telemetry.performance import Measurement, PerformanceSnapshot, save_snapshot


def ask(directory, owner, project, request, *, seconds=2.0, model="test-local"):
    receipt = {
        "request_id": request,
        "context_pack_id": str(uuid4()),
        "state": "COMPLETED",
        "offline": True,
        "response_retained": False,
        "model_ref": model,
        "usage": {"elapsed_seconds": seconds},
        "sources": [{"private": "NEVER_COPY_PRIVATE_SOURCE"}],
    }
    return capture_ask_metrics(directory, owner, project, request, receipt)


def other_mode(directory, owner, project, mode, metric, value, scope):
    # Exact existing sanitized source shape identifiers, explicitly synthetic
    # fixtures. These are saved metrics, not claims of actual Build/research runs.
    directory.mkdir(mode=0o700)
    (directory / "sources").mkdir(mode=0o700)
    raw = json.dumps(
        {
            "schema_version": 1,
            "kind": f"derived-{mode}-runtime-metrics",
            "authority": "DERIVED_MEASUREMENTS_ONLY",
            "owner_id": owner,
            "project_id": project,
            "goal_id" if mode == "build" else "request_id": str(uuid4()),
        }
    ).encode()
    digest = hashlib.sha256(raw).hexdigest()
    path = directory / "sources" / digest
    path.write_bytes(raw)
    path.chmod(0o600)
    measurement = Measurement(
        metric=metric,
        value=value,
        unit="seconds",
        samples=2 if mode == "build" else 1,
        scope=scope,
        evidence="sources/" + digest,
        evidence_sha256=digest,
    )
    save_snapshot(
        directory,
        PerformanceSnapshot(
            captured_at=datetime.now(UTC),
            observations=(measurement,),
            missing_areas=("semantic_accuracy",),
        ),
    )


def test_cli_saved_cross_mode_overview_keeps_quantile_scope_and_original_unknowns(tmp_path):
    owner, project = str(uuid4()), str(uuid4())
    ask(tmp_path / "ask", owner, project, str(uuid4()))
    other_mode(
        tmp_path / "build", owner, project, "build", "latency.invocation_lifecycle_p95", 8.0, "runtime_native-tool"
    )
    other_mode(
        tmp_path / "research",
        owner,
        project,
        "research",
        "latency.research_synthesis_lifecycle",
        5.0,
        "runtime_research",
    )
    runner = CliRunner()
    args = ["metrics", "overview"]
    for name in ("ask", "build", "research"):
        args.extend(["--directory", str(tmp_path / name)])
    args.extend(["--output", str(tmp_path / "overviews"), "--json"])
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert {e["mode"] for e in report["entries"]} == {"ASK", "BUILD", "DELEGATE"}
    build = next(e for e in report["entries"] if e["mode"] == "BUILD")
    assert build["measurement"]["value"] == 8.0 and build["measurement"]["samples"] == 2
    assert build["distinct_records"] == 1  # A within-goal quantile is not two cross-goal observations.
    assert all(
        e["measurement"]["value"] is None
        for e in report["entries"]
        if e["measurement"]["metric"] in {"quality.correct_fraction", "cost.actual"}
    )
    saved = next((tmp_path / "overviews").glob("overview-*.json"))
    original = saved.read_bytes()
    assert json.loads(original) == report and saved.stat().st_mode & 0o777 == 0o600
    assert b"NEVER_COPY_PRIVATE_SOURCE" not in original and "pooled_latency_distribution" in report["missing_areas"]
    assert runner.invoke(app, args).exit_code == 0
    assert saved.read_bytes() == original and len(list((tmp_path / "overviews").glob("*.json"))) == 2
    # Reports cannot pollute the input snapshot schema/history.
    same = runner.invoke(
        app, ["metrics", "overview", "--directory", str(tmp_path / "ask"), "--output", str(tmp_path / "ask")]
    )
    assert same.exit_code == 1 and "UNAVAILABLE" in same.output


def test_recaptures_count_original_requests_once_and_keep_projects_models_and_latest_unknown_distinct(tmp_path):
    directory = tmp_path / "history"
    owner, project, request = str(uuid4()), str(uuid4()), str(uuid4())
    ask(directory, owner, project, request)
    ask(directory, owner, project, request)  # New capture, same original request; no extra measured sample.
    ask(directory, owner, project, str(uuid4()), seconds=4.0)
    ask(directory, owner, str(uuid4()), str(uuid4()), seconds=9.0)
    ask(directory, owner, project, str(uuid4()), model="different-local", seconds=12.0)
    overview = runtime_overview((directory,))
    latency = [e for e in overview.entries if e.measurement.metric == "latency.ask_generation"]
    assert len(latency) == 3
    own = next(e for e in latency if str(e.project_id) == project and e.measurement.model == "test-local")
    assert own.distinct_records == 2 and own.measurement.samples == 1 and own.measurement.value == 4.0
    # A later saved UNKNOWN must not silently display an older successful value.
    source = own.measurement.model_copy(update={"value": None, "samples": 0, "reason": "INCOMPLETE_RUN"})
    save_snapshot(
        directory,
        PerformanceSnapshot(
            captured_at=datetime.now(UTC) + timedelta(seconds=1),
            observations=(source,),
            missing_areas=(),
        ),
    )
    latest = next(
        e
        for e in runtime_overview((directory,)).entries
        if e.measurement.metric == source.metric
        and str(e.project_id) == project
        and e.measurement.model == "test-local"
    )
    assert latest.measurement.value is None and latest.distinct_records == 2


def test_corrupt_source_symlink_unsafe_metadata_or_full_storage_refuses_without_rewriting_history(tmp_path):
    directory = tmp_path / "history"
    captured = ask(directory, str(uuid4()), str(uuid4()), str(uuid4()))
    report = runtime_overview((directory,))
    output = tmp_path / "overviews"
    first = save_overview(output, report)
    before = first.read_bytes()
    filler = output / "owner-retained.data"
    with filler.open("wb") as stream:
        stream.truncate(16 * 1024 * 1024)
    with pytest.raises(ValueError, match="budget"):
        save_overview(output, report)
    assert first.read_bytes() == before and filler.exists()
    link = tmp_path / "alias"
    link.symlink_to(directory, target_is_directory=True)
    with pytest.raises(ValueError, match="path"):
        runtime_overview((link,))
    path = directory / "sources" / captured["source_sha256"]
    original = path.read_bytes()
    path.write_bytes(original + b" ")
    with pytest.raises(ValueError, match="hash"):
        runtime_overview((directory,))
    path.write_bytes(original)
    snapshot = PerformanceSnapshot(captured_at=datetime.now(UTC), observations=(), missing_areas=("\x1b[2J",))
    save_snapshot(directory, snapshot)
    result = CliRunner().invoke(app, ["metrics", "overview", "--directory", str(directory)])
    assert result.exit_code == 1 and "\x1b" not in result.output
    assert first.read_bytes() == before
