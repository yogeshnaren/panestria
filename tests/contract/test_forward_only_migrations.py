"""ADR 0016 decision 5: the product CLI exposes no downgrade; rollback means restoring a backup."""

from __future__ import annotations

import ast
import importlib.util
from collections.abc import Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location("compat", ROOT / "tools/compat.py")
assert _SPEC and _SPEC.loader
compat = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(compat)

_FORBIDDEN = ("downgrade", "rollback", "roll-back", "roll_back")


def _names(node: dict[str, Any], path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], str]]:
    """Every command name and option spelling in the recursive CLI tree, hidden ones included."""
    for param in node["params"]:
        for spelling in [param["name"], *param["opts"]]:
            yield path, spelling
    for name, child in node.get("commands", {}).items():
        yield (*path, name), name
        yield from _names(child, (*path, name))


def test_no_cli_command_or_option_downgrades_the_schema() -> None:
    surface = compat.cli_surface()
    names = list(_names(surface))
    assert len(names) > 50, "CLI tree walk found too little to be meaningful"
    offending = [(" ".join(path), name) for path, name in names if any(word in name.lower() for word in _FORBIDDEN)]
    assert offending == []


def test_no_product_module_can_run_an_alembic_downgrade() -> None:
    offending: list[str] = []
    for path in sorted((ROOT / "src/panestria").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
            relative = path.relative_to(ROOT)
            if isinstance(node, ast.Constant) and node.value == "downgrade":
                offending.append(f"{relative}:{node.lineno} literal 'downgrade'")
            elif isinstance(node, ast.Attribute) and node.attr == "downgrade":
                offending.append(f"{relative}:{node.lineno} .downgrade")
            elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("alembic"):
                if any(alias.name == "downgrade" for alias in node.names):
                    offending.append(f"{relative}:{node.lineno} imports downgrade")
    assert offending == []
