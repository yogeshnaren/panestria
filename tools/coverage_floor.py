"""Combine per-lane coverage data and enforce per-package floors.

Coverage is a floor, not a goal: each critical package may never drop below its
recorded line and branch percentages. Floors only move up; `--write` proposes
new floors from a measured run (measured minus one point, never below the old
floor). Lanes record data with `tools/ci_tests.py SUITE --coverage`.

Floors describe the whole non-live suite, so they are enforced only on full-profile
runs (pushes to main, nightly, full dispatch). A pull request's required profile
selects tests by the changed files; `--report-only` prints its measurement.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLOORS = ROOT / "docs/testing/coverage-floors.json"
PREFIX = "src/panestria/"


def package_of(path: str) -> str:
    """Map `src/panestria/kernel/x.py` to `kernel`; top-level modules to `(top-level)`."""
    relative = path.split(PREFIX, 1)[-1]
    return relative.split("/", 1)[0] if "/" in relative else "(top-level)"


def measure(report: dict[str, object]) -> dict[str, dict[str, float]]:
    """Return per-package line and branch percentages from a `coverage json` report."""
    totals: dict[str, list[int]] = {}
    files = report["files"]
    assert isinstance(files, dict)
    for path, data in files.items():
        summary = data["summary"]
        bucket = totals.setdefault(package_of(path), [0, 0, 0, 0])
        bucket[0] += summary["covered_lines"]
        bucket[1] += summary["num_statements"]
        bucket[2] += summary.get("covered_branches", 0)
        bucket[3] += summary.get("num_branches", 0)
    return {
        name: {
            "line": round(100 * covered / max(statements, 1), 1),
            "branch": round(100 * branches / max(total_branches, 1), 1),
        }
        for name, (covered, statements, branches, total_branches) in sorted(totals.items())
    }


def violations(measured: dict[str, dict[str, float]], floors: dict[str, dict[str, float]]) -> list[str]:
    """Return a message for every package whose measured coverage is below its floor."""
    problems = []
    for name, floor in sorted(floors.items()):
        actual = measured.get(name)
        if actual is None:
            problems.append(f"{name}: no coverage data")
            continue
        for kind in ("line", "branch"):
            if actual[kind] < floor[kind]:
                problems.append(f"{name}: {kind} {actual[kind]}% < floor {floor[kind]}%")
    return problems


def raised(measured: dict[str, dict[str, float]], floors: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    """Propose floors one point below the measurement, never lowering an existing floor."""
    return {
        name: {
            kind: max(floors.get(name, {}).get(kind, 0.0), round(max(value[kind] - 1, 0.0), 1))
            for kind in ("line", "branch")
        }
        for name, value in measured.items()
    }


def combine(data_files: list[Path]) -> dict[str, object]:
    """Combine coverage data files and return the JSON report."""
    output = ROOT / "evidence/coverage.json"
    combined = ROOT / "evidence/coverage-combined"
    data_arg = ["--data-file", str(combined)]
    subprocess.run(
        [sys.executable, "-m", "coverage", "combine", "--keep", *data_arg, *map(str, data_files)], cwd=ROOT, check=True
    )
    subprocess.run([sys.executable, "-m", "coverage", "json", *data_arg, "-o", str(output)], cwd=ROOT, check=True)
    return json.loads(output.read_text())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data", nargs="+", type=Path, help="coverage data files from each lane")
    parser.add_argument("--write", action="store_true", help="raise floors from this measurement")
    parser.add_argument("--report-only", action="store_true", help="print the measurement without enforcing floors")
    args = parser.parse_args()
    measured = measure(combine(args.data))
    document = json.loads(FLOORS.read_text())
    floors = document["floors"]
    for name, value in measured.items():
        print(f"{name:14} line {value['line']:5.1f}%  branch {value['branch']:5.1f}%")
    if args.write:
        document["floors"] = raised(measured, floors)
        FLOORS.write_text(json.dumps(document, indent=2) + "\n")
        return 0
    problems = violations(measured, floors)
    for problem in problems:
        print(f"{'coverage_below_floor_not_enforced' if args.report_only else 'coverage_floor_violation'}: {problem}")
    return 1 if problems and not args.report_only else 0


if __name__ == "__main__":
    sys.exit(main())
