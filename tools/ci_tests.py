"""Run full or explicitly required non-live coverage across isolated CI runners.

Files retain their original paths and release-case registrations. New unit and
contract files go to fast; new integration files default to platform. This is
file-level partitioning. Required CI defers only reviewed named regressions;
unknown/new tests remain included. Local default/full and release tests remain.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUITES = ("fast", "kernel", "platform", "research")
# Keep durable Build/queue integration with kernel recovery, leaving physical
# browser/profile/native checks in platform. All files still run exactly once.
KERNEL = (
    "test_aos_001",
    "test_aos_002",
    "test_aos_003",
    "test_aos_004",
    "test_r0_",
    "test_background_",
    "test_build_",
    "test_canonical_plan_",
    "test_plan_",
    "test_final_plan_",
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


def deferred_nodes(profile: str, base: str | None) -> tuple[list[dict[str, str]], str, list[str] | None]:
    if profile == "full":
        return [], "explicit_full", None
    if base is None or re.fullmatch(r"[0-9a-f]{40}", base) is None:
        return [], "unknown_base_full_fallback", None
    try:
        changed = (
            subprocess.check_output(
                ["git", "diff", "--name-only", "-z", base, "HEAD"],
                cwd=ROOT,
                timeout=5,
            )
            .decode()
            .split("\0")
        )
    except (subprocess.SubprocessError, UnicodeError):
        return [], "unavailable_base_full_fallback", None
    policy = json.loads((ROOT / "docs/testing/ci-regression-policy.json").read_text())
    if policy["schema_version"] != 1:
        raise ValueError("Unknown CI policy version")
    common = policy["full_on_change"]
    deferred, seen = [], set()
    witnesses = json.loads((ROOT / "docs/testing/mutation-critical.json").read_text())["tests"]
    for group in policy["groups"]:
        nodes = group["tests"]
        if not nodes or not group["watch"] or not group["reason"]:
            raise ValueError("Incomplete regression policy")
        promoted = any(fnmatch.fnmatchcase(path, glob) for path in changed for glob in [*common, *group["watch"]])
        promoted = promoted or any(node.split("::")[0] in changed for node in nodes)
        for node in nodes:
            file, name = node.split("::")
            path = ROOT / file
            if node in seen or Path(file).is_absolute() or ".." in Path(file).parts or not file.startswith("tests/"):
                raise ValueError("Unsafe/duplicate regression selector")
            seen.add(node)
            functions = [
                n.name
                for n in ast.parse(path.read_text()).body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            if functions.count(name) != 1 or not name.startswith("test_"):
                raise ValueError("Stale regression selector; review rather than silently omitting coverage")
            if any(n != name and n.startswith(name) for n in functions):
                raise ValueError("Ambiguous deselection prefix; new tests must not be silently omitted")
            if any(w == node or w.startswith(node + "[") for w in witnesses):
                raise ValueError("Mutation witness cannot be deferred")
            if not promoted:
                deferred.append({"node": node, "group": group["id"], "reason": group["reason"]})
    return deferred, "reviewed_required", [p for p in changed if p]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", choices=SUITES)
    parser.add_argument("--list", action="store_true", help="Print the complete file partition without running tests")
    parser.add_argument("--collect-only", action="store_true", help="Collect this suite without setting up fixtures")
    parser.add_argument("--profile", choices=("required", "full"), default="full")
    parser.add_argument("--base", help="Exact comparison commit for required profile; unknown base runs full")
    parser.add_argument("--critical", action="store_true", help="Fast mutation-witness subset; never a full CI pass")
    args = parser.parse_args()
    suites = partition()
    if args.list:
        print(json.dumps(suites, indent=2))
        return 0
    selected = suites[args.suite]
    deferred, reason, changed = deferred_nodes(args.profile, args.base)
    deferred = [d for d in deferred if d["node"].split("::")[0] in selected]
    suffix = ""
    if args.critical:
        if args.suite != "fast":
            parser.error("--critical applies only to fast; it cannot replace full CI")
        selected = json.loads((ROOT / "docs/testing/mutation-critical.json").read_text())["tests"]
        if not selected or any(node.split("::")[0] not in suites["fast"] for node in selected):
            raise ValueError("Critical witness test no longer belongs to the fast suite; refresh mutation evidence")
        suffix = "-critical"
        deferred = []
    plan = {
        "profile": "mutation-witness-only" if args.critical else args.profile,
        "base": args.base,
        "selection_reason": reason,
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "policy_sha256": hashlib.sha256((ROOT / "docs/testing/ci-regression-policy.json").read_bytes()).hexdigest(),
        "changed_files": changed,
        "suite": args.suite,
        "files": selected,
        "deferred": deferred,
        "live": "EXCLUDED_SEPARATE_AUTHORIZED_VALIDATION",
        "release_gate": "NOT_EVALUATED",
    }
    plan_path = ROOT / f"evidence/ci-{args.suite}{suffix}-selection.json"
    plan_path.parent.mkdir(exist_ok=True)
    plan_path.write_text(json.dumps(plan, indent=2) + "\n")
    command = [
        sys.executable,
        "-m",
        "pytest",
        *selected,
        "-m",
        "not live",
        "--durations=25",
        f"--junitxml=evidence/ci-{args.suite}{suffix}.xml",
    ]
    if args.collect_only:
        command.append("--collect-only")
    for item in deferred:
        command += ["--deselect", item["node"]]
    return subprocess.run(command, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
