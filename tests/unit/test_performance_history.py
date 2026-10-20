"""Real retained observations remain historical; persistence never invents a pass."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from panestria.cli.main import app
from panestria.telemetry.performance import Measurement, collect_performance, latest_snapshot, save_snapshot

ROOT = Path(__file__).resolve().parents[2]


def test_actual_historical_models_keep_separate_rubrics_quality_latency_and_unknown_cost():
    snapshot = collect_performance(ROOT / "evidence")
    quality = [x for x in snapshot.observations if x.metric == "quality.correct_fraction" and x.fold == "qualification"]
    local, native = quality
    assert local.value == pytest.approx(21 / 36) and native.value == pytest.approx(33 / 36)
    assert local.samples == native.samples == 36
    assert local.source_commit == "bf3cb4260867c2822f789b35b6464a7aea5e25ad"
    assert native.source_commit == "98927690d37bd0b73a07278957db6e142fb14389"
    assert local.rubric_sha256 != native.rubric_sha256
    assert local.model == "qwen2.5:1.5b-instruct" and native.model == "claude-haiku-4-5-20251001"
    assert all(x.value is None and x.reason == "UNMEASURED" for x in snapshot.observations if x.metric == "cost.actual")
    assert all(
        x.value is None for x in snapshot.observations if x.metric.startswith("latency.case") and "native" in x.scope
    )
    assert all(x.value > 0 for x in snapshot.observations if x.metric.startswith("latency.case") and "local" in x.scope)
    assert "build_success_and_false_done_rate" in snapshot.missing_areas


def test_private_capture_is_append_only_readable_and_has_no_raw_prompts(tmp_path):
    directory = tmp_path / "history"
    runner = CliRunner()
    args = ["metrics", "capture", "--evidence-root", str(ROOT / "evidence"), "--directory", str(directory)]
    first = runner.invoke(app, args)
    assert first.exit_code == 0, first.output
    path = Path(json.loads(first.output)["path"])
    original = path.read_bytes()
    assert runner.invoke(app, args).exit_code == 0
    assert path.read_bytes() == original and len(list(directory.glob("*.json"))) == 2
    assert directory.stat().st_mode & 0o777 == 0o700 and path.stat().st_mode & 0o777 == 0o600
    shown = runner.invoke(app, ["metrics", "show", "--directory", str(directory), "--json"])
    assert shown.exit_code == 0 and json.loads(shown.output)["authority"] == "DERIVED_MEASUREMENTS_ONLY"
    assert not any(field in json.loads(shown.output) for field in ("release_pass", "prompt", "answer"))
    assert latest_snapshot(directory).model_dump(mode="json") == json.loads(shown.output)


def test_incomplete_mutation_run_cannot_be_promoted_to_a_detection_score(tmp_path):
    report = {
        "kind": "mutation_pilot",
        "authority": "TEST_EFFECTIVENESS_ONLY",
        "baseline_passed": True,
        "exit_code": 0,
        "source_commit": "ab" * 20,
        "dirty": False,
        "mutants": [{"status": "DETECTED"}, {"status": "SURVIVED"}, {"status": "UNRESOLVED"}],
    }
    path = tmp_path / "mutation.json"
    path.write_text(json.dumps(report))
    incomplete = collect_performance(tmp_path, mutation_reports=(path,))
    score = next(x for x in incomplete.observations if x.metric == "testing.mutation_detection")
    assert score.value is None and score.reason == "INCOMPLETE_RUN" and score.samples == 3
    report["mutants"].pop()
    path.write_text(json.dumps(report))
    complete = collect_performance(tmp_path, mutation_reports=(path,))
    assert complete.observations[0].value == 0.5 and complete.observations[1].value == 1


def test_storage_budget_and_symlink_never_overwrite_or_delete_history(tmp_path):
    snapshot = collect_performance(ROOT / "evidence")
    directory = tmp_path / "history"
    path = save_snapshot(directory, snapshot)
    body = path.read_bytes()
    filler = directory / "owner-retained.data"
    with filler.open("wb") as stream:
        stream.truncate(16 * 1024 * 1024)
    with pytest.raises(ValueError, match="budget"):
        save_snapshot(directory, snapshot)
    assert path.read_bytes() == body and filler.stat().st_size == 16 * 1024 * 1024
    link = tmp_path / "link"
    link.symlink_to(directory, target_is_directory=True)
    with pytest.raises(ValueError, match="private"):
        save_snapshot(link, snapshot)


@pytest.mark.parametrize(
    "change",
    [{"value": float("nan")}, {"value": -1}, {"value": 2}, {"value": None}, {"unit": "USD"}, {"samples": True}],
)
def test_values_cannot_conflate_unknown_invalid_units_or_fake_fraction_precision(change):
    point = collect_performance(ROOT / "evidence").observations[0].model_dump()
    with pytest.raises(ValueError):
        Measurement.model_validate({**point, **change})
