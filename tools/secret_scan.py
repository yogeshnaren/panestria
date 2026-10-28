"""Fail if tracked files (or, with --history, any committed change) contain secret material.

The default scan skips the synthetic sentinel fixture. A finding prints the
path (or commit) and rule name, never the matched text.

    python tools/secret_scan.py              # tracked files
    python tools/secret_scan.py PATH...      # explicit files
    python tools/secret_scan.py --history    # lines added anywhere in git history
"""

from __future__ import annotations

import json
import math
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SENTINEL = Path("tests/fixtures/boundaries/secret_sentinel.txt")
ALLOWLIST = ROOT / "docs/testing/secret-scan-allowlist.json"
# Split literals keep this file from matching its own rules.
RULES = (
    ("private-key", re.compile("-----BEGIN " + r"(?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----")),
    ("aws-access-key-id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("anthropic-api-key", re.compile("sk-" + r"ant-[A-Za-z0-9_-]{20,}")),
    ("openai-api-key", re.compile(r"\bsk-(?:proj|svcacct|admin)-[A-Za-z0-9_-]{20,}|\bsk-[A-Za-z0-9]{48}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{22,}")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
)
# NAME_KEY = "value" style assignments are reported only when the value looks random.
ASSIGNMENT = re.compile(r"(?i)\b[A-Z0-9_]*(?:API_?KEY|SECRET|TOKEN|PASSWORD)\b\s*[:=]\s*[\"']?([A-Za-z0-9/+_-]{24,})")
MIN_ENTROPY = 4.0


def entropy(value: str) -> float:
    """Return the Shannon entropy of ``value`` in bits per character."""
    counts = Counter(value)
    return -sum(n / len(value) * math.log2(n / len(value)) for n in counts.values())


def rules_matching(text: str) -> list[str]:
    """Return the names of every rule that matches ``text``."""
    found = [name for name, pattern in RULES if pattern.search(text)]
    if any(entropy(match.group(1)) >= MIN_ENTROPY for match in ASSIGNMENT.finditer(text)):
        found.append("high-entropy-assignment")
    return found


def allowed() -> set[tuple[str, str]]:
    """Return reviewed (path, rule) pairs from the allowlist."""
    return {(entry["path"], entry["rule"]) for entry in json.loads(ALLOWLIST.read_text())["allow"]}


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
    allow = allowed()
    commit = path = ""
    for line in log.splitlines():
        if line.startswith("commit "):
            commit = line[7:]
        elif line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else line[4:]
        elif line.startswith("+") and path != str(SENTINEL):
            findings.update((commit, path, name) for name in rules_matching(line[1:]) if (path, name) not in allow)
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
