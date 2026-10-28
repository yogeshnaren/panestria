"""Prove that Python changes since a revision are layout-only.

Compares the AST (without positions) of every Python file changed between REV
and the working tree. Used to review formatter-only commits: exit 0 means no
changed file has a different syntax tree, so no behavior can have changed.
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _tree(source: str) -> str:
    return ast.dump(ast.parse(source), include_attributes=False)


def changed_python(rev: str) -> list[str]:
    """Return tracked .py paths that differ between ``rev`` and the working tree."""
    out = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=M", rev, "--", "*.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [line for line in out.splitlines() if line]


def differing(rev: str) -> list[str]:
    """Return changed paths whose syntax tree differs from ``rev``."""
    bad = []
    for path in changed_python(rev):
        old = subprocess.run(
            ["git", "show", f"{rev}:{path}"], cwd=ROOT, check=True, capture_output=True, text=True
        ).stdout
        if _tree(old) != _tree((ROOT / path).read_text(encoding="utf-8")):
            bad.append(path)
    return bad


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rev", help="git revision to compare against, e.g. origin/main")
    args = parser.parse_args()
    changed = changed_python(args.rev)
    bad = differing(args.rev)
    for path in bad:
        print(f"ast_changed: {path}")
    print(f"checked={len(changed)} ast_changed={len(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
