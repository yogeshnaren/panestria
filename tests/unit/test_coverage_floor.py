"""Coverage floors only ratchet upward and fail on any per-package regression."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "coverage_floor", Path(__file__).resolve().parents[2] / "tools/coverage_floor.py"
)
assert _SPEC and _SPEC.loader
coverage_floor = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(coverage_floor)


def _file(lines: int, covered: int, branches: int = 0, covered_branches: int = 0) -> dict[str, object]:
    return {
        "summary": {
            "num_statements": lines,
            "covered_lines": covered,
            "num_branches": branches,
            "covered_branches": covered_branches,
        }
    }


def test_measure_groups_files_by_package_and_top_level_modules() -> None:
    report = {
        "files": {
            "src/panestria/kernel/a.py": _file(10, 5, 4, 1),
            "src/panestria/kernel/b.py": _file(10, 10, 4, 4),
            "src/panestria/config.py": _file(4, 1),
        }
    }
    assert coverage_floor.measure(report) == {
        "(top-level)": {"line": 25.0, "branch": 0.0},
        "kernel": {"line": 75.0, "branch": 62.5},
    }


def test_any_line_or_branch_drop_or_missing_package_is_a_violation() -> None:
    floors = {"kernel": {"line": 70.0, "branch": 60.0}, "api": {"line": 10.0, "branch": 1.0}}
    measured = {"kernel": {"line": 70.0, "branch": 59.9}}
    assert coverage_floor.violations(measured, floors) == [
        "api: no coverage data",
        "kernel: branch 59.9% < floor 60.0%",
    ]
    assert coverage_floor.violations({"kernel": {"line": 70.0, "branch": 60.0}}, {"kernel": floors["kernel"]}) == []


def test_floors_rise_one_point_below_measurement_and_never_fall() -> None:
    floors = {"kernel": {"line": 80.0, "branch": 10.0}}
    measured = {"kernel": {"line": 75.0, "branch": 50.0}, "api": {"line": 0.5, "branch": 0.0}}
    assert coverage_floor.raised(measured, floors) == {
        "kernel": {"line": 80.0, "branch": 49.0},
        "api": {"line": 0.0, "branch": 0.0},
    }


def test_report_only_prints_violations_but_succeeds(tmp_path, monkeypatch, capsys) -> None:
    floors = tmp_path / "floors.json"
    floors.write_text('{"schema_version": 1, "floors": {"kernel": {"line": 90.0, "branch": 90.0}}}')
    monkeypatch.setattr(coverage_floor, "FLOORS", floors)
    monkeypatch.setattr(
        coverage_floor, "combine", lambda _files: {"files": {"src/panestria/kernel/a.py": _file(10, 5)}}
    )
    monkeypatch.setattr("sys.argv", ["coverage_floor.py", "--report-only", "lane"])
    assert coverage_floor.main() == 0
    assert "coverage_below_floor_not_enforced: kernel: line 50.0% < floor 90.0%" in capsys.readouterr().out
    monkeypatch.setattr("sys.argv", ["coverage_floor.py", "lane"])
    assert coverage_floor.main() == 1
    assert "coverage_floor_violation: kernel" in capsys.readouterr().out


def test_tolerance_allows_only_the_documented_shortfall() -> None:
    floors = {"learning": {"line": 88.1, "branch": 72.4}}
    assert coverage_floor.violations({"learning": {"line": 88.1, "branch": 70.4}}, floors, 2.0) == []
    assert coverage_floor.violations({"learning": {"line": 88.1, "branch": 70.3}}, floors, 2.0) == [
        "learning: branch 70.3% < floor 72.4%"
    ]


def _selection(tmp_path, name: str, deferred: object) -> str:
    path = tmp_path / f"ci-{name}-selection.json"
    path.write_text(json.dumps({"profile": "required", "deferred": deferred}))
    return str(path)


def test_deferred_regressions_enable_the_tolerance_and_exact_runs_do_not(tmp_path, monkeypatch, capsys) -> None:
    floors = tmp_path / "floors.json"
    floors.write_text(
        '{"schema_version": 1, "deferred_tolerance_points": 2.0, "floors": {"kernel": {"line": 51.0, "branch": 0.0}}}'
    )
    monkeypatch.setattr(coverage_floor, "FLOORS", floors)
    monkeypatch.setattr(
        coverage_floor, "combine", lambda _files: {"files": {"src/panestria/kernel/a.py": _file(10, 5)}}
    )
    deferring = _selection(tmp_path, "kernel", [{"node": "tests/x.py::test_a"}])
    exact = _selection(tmp_path, "fast", [])
    monkeypatch.setattr("sys.argv", ["coverage_floor.py", "--selection", exact, "--selection", deferring, "lane"])
    assert coverage_floor.main() == 0
    out = capsys.readouterr().out
    assert "coverage_floor_mode: 1 deferred regressions, tolerance 2.0 points" in out
    assert "coverage_below_floor_within_deferral_tolerance: kernel: line 50.0% < floor 51.0%" in out
    monkeypatch.setattr("sys.argv", ["coverage_floor.py", "--selection", exact, "lane"])
    assert coverage_floor.main() == 1
    out = capsys.readouterr().out
    assert "coverage_floor_mode: nothing deferred, exact floors" in out
    assert "coverage_floor_violation: kernel: line 50.0% < floor 51.0%" in out


def test_unreadable_selection_fails_instead_of_relaxing(tmp_path) -> None:
    with pytest.raises(ValueError, match="no deferred list"):
        coverage_floor.deferred_count([Path(_selection(tmp_path, "kernel", None))])
    with pytest.raises(FileNotFoundError):
        coverage_floor.deferred_count([tmp_path / "missing.json"])
