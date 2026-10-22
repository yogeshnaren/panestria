"""Run every non-live behavioral test once across isolated CI runners.

Files retain their original paths and release-case registrations. New unit and
contract files go to fast; new integration files default to platform. This is
file-level partitioning, not a changed-files heuristic or a smoke-test allowlist.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUITES = ("fast", "kernel", "platform", "research")
# Keep durable Build/queue integration with kernel recovery, leaving physical
# browser/profile/native checks in platform. All files still run exactly once.
KERNEL = (
    "test_aos_001", "test_aos_002", "test_aos_003", "test_aos_004", "test_r0_",
    "test_background_", "test_build_", "test_canonical_plan_", "test_plan_", "test_final_plan_",
)
RESEARCH = (
    "test_research_",
    "test_owner_research_",
    "test_search_",
    "test_fetch_",
    "test_isolated_",
    "test_pdf_",
    "test_public_web_",
    "test_configured_search",
    "test_shared_research_runtime",
)


def partition() -> dict[str, list[str]]:
    suites: dict[str, list[str]] = {name: [] for name in SUITES}
    with (ROOT / "pyproject.toml").open("rb") as stream:
        options = tomllib.load(stream)["tool"]["pytest"]["ini_options"]
    patterns = options.get("python_files", ["test_*.py", "*_test.py"])
    if isinstance(patterns, str):
        patterns = patterns.split()
    if not isinstance(patterns, list) or not patterns or not all(isinstance(p, str) and p for p in patterns):
        raise ValueError("Invalid pytest file patterns")
    for path in sorted((ROOT / "tests").rglob("*.py")):
        if not any(fnmatch.fnmatchcase(path.name, pattern) for pattern in patterns):
            continue
        relative = path.relative_to(ROOT)
        directory = relative.parts[1]
        if directory in ("unit", "contract"):
            suite = "fast"
        elif directory == "e2e":
            suite = "kernel"
        elif directory != "integration":
            raise ValueError(f"Unassigned test directory: {relative}")
        elif path.name.startswith(KERNEL):
            suite = "kernel"
        elif path.name.startswith(RESEARCH):
            suite = "research"
        else:
            suite = "platform"
        suites[suite].append(str(relative))
    if not all(suites.values()):
        raise ValueError("CI suite is empty")
    return suites


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", choices=SUITES)
    parser.add_argument("--list", action="store_true", help="Print the complete file partition without running tests")
    parser.add_argument("--collect-only", action="store_true", help="Collect this suite without setting up fixtures")
    parser.add_argument("--critical", action="store_true", help="Fast mutation-witness subset; never a full CI pass")
    args = parser.parse_args()
    suites = partition()
    if args.list:
        print(json.dumps(suites, indent=2))
        return 0
    selected = suites[args.suite]
    suffix = ""
    if args.critical:
        if args.suite != "fast":
            parser.error("--critical applies only to fast; it cannot replace full CI")
        selected = json.loads((ROOT / "docs/testing/mutation-critical.json").read_text())["tests"]
        if not selected or any(node.split("::")[0] not in suites["fast"] for node in selected):
            raise ValueError("Critical witness test no longer belongs to the fast suite; refresh mutation evidence")
        suffix = "-critical"
    command = [
        sys.executable, "-m", "pytest", *selected,
        "-m", "not live", "--durations=25", f"--junitxml=evidence/ci-{args.suite}{suffix}.xml",
    ]
    if args.collect_only:
        command.append("--collect-only")
    return subprocess.run(command, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
