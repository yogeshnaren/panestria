"""Snapshot Panestria's externally visible surfaces and diff them against a baseline.

Behavior-preserving refactors must leave every surface unchanged. The surfaces
are the HTTP API (OpenAPI), the CLI command tree, typed denial codes, the DB
schema fingerprint, exported contract schemas, the package import graph and,
when JUnit reports are given, the set of passing test nodes. Feature PRs list
intended differences in docs/testing/compat-exceptions.json; any other
difference fails `check`.

    python tools/compat.py snapshot --output snapshot.json [--junit evidence/ci-*.xml]
    python tools/compat.py check --baseline snapshot.json [--junit evidence/ci-*.xml]
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src/panestria"
EXCEPTIONS = ROOT / "docs/testing/compat-exceptions.json"
CLI_SURFACE = ROOT / "docs/api/cli-surface.json"
_DENIAL_SUFFIXES = ("Denied", "Rejected", "Unavailable")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cli_surface() -> dict[str, Any]:
    """Return the recursive command tree: commands, parameters, flags and visibility."""
    # Typer ships its own click; walk the tree by duck typing, not click classes.
    import typer

    from panestria.cli.main import app

    def describe(command: Any) -> dict[str, Any]:
        node: dict[str, Any] = {
            "hidden": bool(getattr(command, "hidden", False)),
            "params": [
                {
                    "name": param.name,
                    "opts": sorted(param.opts),
                    "kind": param.param_type_name,
                    "required": bool(param.required),
                    "type": param.type.name,
                }
                for param in command.params
                if param.name != "help"
            ],
        }
        if hasattr(command, "commands"):
            node["commands"] = {name: describe(sub) for name, sub in sorted(command.commands.items())}
        return node

    return describe(typer.main.get_command(app))


def denial_codes() -> list[str]:
    """Return every literal code passed to a *Denied/*Rejected/*Unavailable exception in src."""
    codes: set[str] = set()
    for path in sorted(SRC.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant)):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name.endswith(_DENIAL_SUFFIXES) and isinstance(node.args[0].value, str):
                codes.add(f"{name}:{node.args[0].value}")
    return sorted(codes)


def import_graph() -> list[str]:
    """Return sorted `package -> package` edges between top-level panestria sub-packages."""
    edges: set[str] = set()
    for path in sorted(SRC.rglob("*.py")):
        relative = path.relative_to(SRC).parts
        source = relative[0].removesuffix(".py") if len(relative) > 1 else "(top-level)"
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = [node.module] if isinstance(node, ast.ImportFrom) and node.module else []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            for name in names:
                parts = name.split(".")
                if parts[0] == "panestria" and len(parts) > 1:
                    target = parts[1] if (SRC / parts[1]).is_dir() else "(top-level)"
                    if target != source:
                        edges.add(f"{source} -> {target}")
    return sorted(edges)


def junit_nodes(reports: list[Path]) -> dict[str, str]:
    """Return {node id: outcome} from JUnit XML reports (passed, failed, error or skipped)."""
    outcomes: dict[str, str] = {}
    for report in reports:
        for case in ET.parse(report).getroot().iter("testcase"):
            node = f"{case.get('classname', '')}::{case.get('name', '')}"
            outcome = "passed"
            for child in case:
                if child.tag in ("failure", "error", "skipped"):
                    outcome = {"failure": "failed"}.get(child.tag, child.tag)
            outcomes[node] = outcome
    return dict(sorted(outcomes.items()))


def snapshot(junit: list[Path]) -> dict[str, Any]:
    """Return the current surface snapshot."""
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    result: dict[str, Any] = {
        "schema_version": 1,
        "source_commit": commit,
        "openapi_sha256": _sha(ROOT / "docs/api/openapi.json"),
        "cli": cli_surface(),
        "denial_codes": denial_codes(),
        "schema_fingerprint_sha256": _sha(ROOT / "migrations/schema_fingerprint.txt"),
        "schema_snapshot_sha256": _sha(ROOT / "docs/contracts/schema-snapshot.txt"),
        "contract_schemas": {p.name: _sha(p) for p in sorted((ROOT / "docs/contracts").glob("*.schema.json"))},
        "import_graph": import_graph(),
    }
    if junit:
        result["junit"] = junit_nodes(junit)
    return result


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        flat: dict[str, Any] = {}
        for key, item in value.items():
            flat.update(_flatten(item, f"{prefix}/{key}" if prefix else str(key)))
        return flat
    if isinstance(value, list):
        return {f"{prefix}[{item}]" if isinstance(item, str) else f"{prefix}#{i}": item for i, item in enumerate(value)}
    return {prefix: value}


def differences(baseline: dict[str, Any], current: dict[str, Any]) -> list[str]:
    """Return human-readable surface differences, ignoring source_commit.

    JUnit is compared one way: a baseline node may not disappear or stop passing;
    new passing nodes are allowed.
    """
    old = {k: v for k, v in _flatten(baseline).items() if not k.startswith(("source_commit", "junit/"))}
    new = {k: v for k, v in _flatten(current).items() if not k.startswith(("source_commit", "junit/"))}
    found = [f"removed {key}" for key in sorted(old.keys() - new.keys())]
    found += [f"added {key}" for key in sorted(new.keys() - old.keys())]
    found += [f"changed {key}" for key in sorted(old.keys() & new.keys()) if old[key] != new[key]]
    if "junit" in baseline and "junit" in current:
        for node, outcome in baseline["junit"].items():
            now = current["junit"].get(node)
            if now is None:
                found.append(f"removed junit/{node}")
            elif outcome == "passed" and now != "passed":
                found.append(f"changed junit/{node} passed->{now}")
    return found


def allowed(found: list[str], exceptions: list[dict[str, str]]) -> list[str]:
    """Drop differences covered by a declared exception prefix; return the rest."""
    prefixes = [entry["match"] for entry in exceptions]
    return [item for item in found if not any(item.startswith(prefix) for prefix in prefixes)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    snap = sub.add_parser("snapshot")
    snap.add_argument("--output", type=Path, required=True)
    snap.add_argument("--junit", type=Path, nargs="*", default=[])
    check = sub.add_parser("check")
    check.add_argument("--baseline", type=Path, required=True)
    check.add_argument("--junit", type=Path, nargs="*", default=[])
    cli = sub.add_parser("cli-surface", help="regenerate docs/api/cli-surface.json")
    cli.add_argument("--check", action="store_true", help="fail if the committed file is stale")
    args = parser.parse_args()
    if args.action == "cli-surface":
        rendered = json.dumps(cli_surface(), indent=2) + "\n"
        if args.check:
            return 0 if CLI_SURFACE.read_text() == rendered else 1
        CLI_SURFACE.write_text(rendered)
        return 0
    if args.action == "snapshot":
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(snapshot(args.junit), indent=2) + "\n")
        return 0
    baseline = json.loads(args.baseline.read_text())
    exceptions = json.loads(EXCEPTIONS.read_text())["exceptions"]
    remaining = allowed(differences(baseline, snapshot(args.junit)), exceptions)
    for item in remaining:
        print(f"undeclared_surface_change: {item}")
    print(f"surface_changes={len(remaining)}")
    return 1 if remaining else 0


if __name__ == "__main__":
    sys.exit(main())
