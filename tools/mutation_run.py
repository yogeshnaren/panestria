"""Fresh, source-bound mutmut pilot; no Docker, inference or owner services."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = [
    "panestria.policy.engine.*authorize*",
    "panestria.sandbox.egress.*public_unicast*",
    "panestria.sandbox.egress.*verify_peer*",
    "panestria.sandbox.egress.*resolve_destination*",
    "panestria.verification.entailment.*score_predictions*",
]


def run(output: Path) -> int:
    output = output.resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    workspace, observations = output / "workspace", output / "observations"
    workspace.mkdir(mode=0o700)
    observations.mkdir(mode=0o700)
    hashes = {}
    # Copy only tracked inputs, never .env, weights, credentials or owner databases.
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    for name in tracked:
        if not name or not (name.startswith(("src/", "tests/", "tools/")) or name in {"pyproject.toml", "uv.lock"}):
            continue
        source = ROOT / name
        if source.is_symlink():
            raise ValueError("symlink_input_refused")
        hashes[name] = hashlib.sha256(source.read_bytes()).hexdigest()
        target = workspace / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    env = {**os.environ, "PYTHONPATH": str(workspace / "tools"),
           "PANESTRIA_MUTATION_OBSERVATIONS": str(observations), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    command = [str(Path(sys.executable).parent / "mutmut"), "run", "--max-children", "2", *PATTERNS]
    started = datetime.now(UTC).isoformat()
    clock = time.monotonic()
    with (output / "run.log").open("w") as log:
        try:
            completed = subprocess.run(
                command, cwd=workspace, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=600
            )
            exit_code = completed.returncode
        except subprocess.TimeoutExpired:
            exit_code = 124
    outcomes = {item["mutant"]: item for path in observations.glob("*.json")
                if (item := json.loads(path.read_text()))}
    mutants = []
    detectors = defaultdict(list)
    for path in (workspace / "mutants").rglob("*.meta"):
        data = json.loads(path.read_text())
        for name, code in data["exit_code_by_key"].items():
            import fnmatch
            if not any(fnmatch.fnmatch(name, pattern) for pattern in PATTERNS):
                continue
            observation = outcomes.get(name, {})
            failures = sorted({call["test"] for call in observation.get("calls", []) if call["outcome"] == "failed"})
            # mutmut also treats pytest INTERNAL_ERROR as killed. Keep that separate.
            status = ("DETECTED" if code == 1 and failures and not observation.get("errors") else
                      "SURVIVED" if code == 0 else "UNRESOLVED")
            for test in failures if status == "DETECTED" else []:
                detectors[test].append(name)
            mutants.append({"id": name, "status": status, "tool_exit_code": code,
                            "failing_calls": failures, "phase_errors": observation.get("errors", [])})
    counts = Counter(item["status"] for item in mutants)
    denominator = counts["DETECTED"] + counts["SURVIVED"]
    report = {
        "schema_version": 1, "kind": "mutation_pilot", "authority": "TEST_EFFECTIVENESS_ONLY",
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)),
        "input_sha256": hashes, "started_at": started, "duration_seconds": time.monotonic() - clock,
        "python": sys.version.split()[0], "mutmut": importlib.metadata.version("mutmut"),
        "command": command[1:], "exit_code": exit_code, "scope": PATTERNS,
        "counts": dict(counts), "selected_mutants": len(mutants),
        "detection_fraction": counts["DETECTED"] / denominator if denominator else None,
        "unresolved_excluded_from_fraction": True,
        "baseline_observations": [v for k, v in outcomes.items() if "__mutmut_" not in k],
        "mutants": sorted(mutants, key=lambda x: x["id"]),
        "detectors": dict(sorted(detectors.items())),
        "limits": ["Five functions only; not repository-wide effectiveness or model accuracy.",
                   "Survivors require review; equivalent or invalid mutants are not silently excluded.",
                   "No test is redundant merely because it detects no fault in this limited scope."],
    }
    path = output / "report.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    path.chmod(0o600)
    print(json.dumps({"report": str(path), "counts": dict(counts), "seconds": report["duration_seconds"]}))
    return 0 if exit_code == 0 and mutants and not counts["UNRESOLVED"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New private campaign directory; never overwritten")
    raise SystemExit(run(parser.parse_args().output))
