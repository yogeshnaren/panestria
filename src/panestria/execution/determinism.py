"""Workflow bodies stay free of clocks, randomness, and direct I/O."""

from __future__ import annotations

import ast
import inspect
import textwrap
from collections.abc import Callable
from typing import cast

_FORBIDDEN = frozenset(
    {
        "create_engine",
        "datetime.now",
        "datetime.utcnow",
        "open",
        "random.randint",
        "random.random",
        "subprocess.Popen",
        "subprocess.run",
        "time.monotonic",
        "time.sleep",
        "time.time",
        "urlopen",
        "uuid.uuid4",
        "uuid4",
    }
)


def workflow_body_violations(function: Callable[..., object]) -> tuple[str, ...]:
    """Names of non-deterministic calls in one workflow body."""
    target = function
    for _ in range(5):
        wrapped = getattr(target, "__wrapped__", None)
        if not callable(wrapped):
            break
        target = cast(Callable[..., object], wrapped)
    source = textwrap.dedent(inspect.getsource(target))
    tree = ast.parse(source)
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func)
        if name in _FORBIDDEN:
            found.append(name)
    return tuple(found)


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return f"{node.value.id}.{node.attr}"
    return ""
