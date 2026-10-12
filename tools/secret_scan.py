"""Fail if tracked files contain obvious secret material.

The default scan skips the synthetic sentinel fixture. A match prints the
path and rule name, not the matched text.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SENTINEL = Path("tests/fixtures/boundaries/secret_sentinel.txt")
RULES = (
    ("private-key", re.compile("-----BEGIN " + "PRIVATE KEY-----")),
    ("aws-access-key-id", re.compile(r"AKIA[0-9A-Z]{16}")),
)


def tracked_files() -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [ROOT / item.decode() for item in completed.stdout.split(b"\0") if item]


def scan(paths: list[Path]) -> list[tuple[Path, str]]:
    findings: list[tuple[Path, str]] = []
    for path in paths:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for name, pattern in RULES:
            if pattern.search(text):
                findings.append((path, name))
    return findings


def main(argv: list[str]) -> int:
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
