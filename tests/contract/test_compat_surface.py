"""The committed CLI surface is current and surface diffs are detected exactly."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location("compat", ROOT / "tools/compat.py")
assert _SPEC and _SPEC.loader
compat = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(compat)


def test_committed_cli_surface_matches_the_installed_cli() -> None:
    assert json.loads((ROOT / "docs/api/cli-surface.json").read_text()) == compat.cli_surface()


def test_surface_differences_are_reported_and_only_declared_ones_are_allowed() -> None:
    baseline = {
        "source_commit": "a",
        "denial_codes": ["KernelDenied:not_found", "KernelDenied:stale"],
        "cli": {"commands": {"ask": {"hidden": False}}},
        "junit": {"t::a": "passed", "t::b": "passed", "t::c": "skipped"},
    }
    current = {
        "source_commit": "b",
        "denial_codes": ["KernelDenied:not_found", "KernelDenied:renamed"],
        "cli": {"commands": {"ask": {"hidden": True}}},
        "junit": {"t::a": "passed", "t::c": "passed", "t::new": "passed"},
    }
    found = compat.differences(baseline, current)
    assert found == [
        "removed denial_codes[KernelDenied:stale]",
        "added denial_codes[KernelDenied:renamed]",
        "changed cli/commands/ask/hidden",
        "removed junit/t::b",
    ]
    declared = [{"match": "changed cli/commands/ask", "reason": "test", "finding": "test"}]
    assert compat.allowed(found, declared) == found[:2] + found[3:]


def test_a_passing_node_that_now_fails_is_a_difference() -> None:
    found = compat.differences({"junit": {"t::a": "passed"}}, {"junit": {"t::a": "failed"}})
    assert found == ["changed junit/t::a passed->failed"]
