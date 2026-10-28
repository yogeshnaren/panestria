"""Fail if tracked files (or, with --history, any committed change) contain secret material.

The default scan skips the synthetic sentinel fixture. A finding prints the
path (or commit) and rule name, never the matched text.

    python tools/secret_scan.py              # tracked files
    python tools/secret_scan.py PATH...      # explicit files
    python tools/secret_scan.py --history    # lines added anywhere in git history
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from panestria.contracts.secret_rules import ASSIGNMENT, MIN_ENTROPY, RULES, entropy, rules_matching

ROOT = Path(__file__).resolve().parents[1]
SENTINEL = Path("tests/fixtures/boundaries/secret_sentinel.txt")
ALLOWLIST = ROOT / "docs/testing/secret-scan-allowlist.json"

__all__ = ["ASSIGNMENT", "MIN_ENTROPY", "RULES", "entropy", "rules_matching"]


def _entries() -> list[dict[str, str]]:
    return list(json.loads(ALLOWLIST.read_text())["allow"])


def allowed() -> set[tuple[str, str]]:
    """Return reviewed (path, rule) pairs that apply to the current tree."""
    return {(entry["path"], entry["rule"]) for entry in _entries() if "commit" not in entry}


def allowed_history() -> set[tuple[str, str, str]]:
    """Return reviewed (commit, path, rule) triples; tree-wide entries apply to every commit."""
    return {(entry.get("commit", "*"), entry["path"], entry["rule"]) for entry in _entries()}


def tracked_files() -> list[Path]:
    completed = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True)
    return [ROOT / item.decode() for item in completed.stdout.split(b"\0") if item]


def scan(paths: list[Path]) -> list[tuple[Path, str]]:
    findings: list[tuple[Path, str]] = []
    allow = allowed()
    for path in paths:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        relative = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
        findings.extend((path, name) for name in rules_matching(text) if (relative, name) not in allow)
    return findings


def scan_history() -> list[tuple[str, str, str]]:
    """Return (commit, path, rule) for lines added in any commit reachable from any ref."""
    log = subprocess.run(
        ["git", "log", "--all", "-p", "--unified=0", "--no-color", "--format=commit %H"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8", errors="replace")
    findings: set[tuple[str, str, str]] = set()
    allow = allowed_history()
    commit = path = ""
    for line in log.splitlines():
        if line.startswith("commit "):
            commit = line[7:]
        elif line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else line[4:]
        elif line.startswith("+") and path != str(SENTINEL):
            findings.update(
                (commit, path, name)
                for name in rules_matching(line[1:])
                if (commit, path, name) not in allow and ("*", path, name) not in allow
            )
    return sorted(findings)


def main(argv: list[str]) -> int:
    if argv == ["--history"]:
        history = scan_history()
        for commit, path, name in history:
            print(f"{commit[:12]} {path}: {name}")
        return 1 if history else 0
    if argv:
        paths = [Path(item).resolve() for item in argv]
    else:
        paths = [path for path in tracked_files() if path != (ROOT / SENTINEL).resolve()]
    findings = scan(paths)
    for path, name in findings:
        print(f"{path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}: {name}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
