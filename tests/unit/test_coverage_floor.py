"""Coverage floors only ratchet upward and fail on any per-package regression."""

from __future__ import annotations

import importlib.util
from pathlib import Path

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
