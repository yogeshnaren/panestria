"""The browser-journey gate reports each missing Node/Playwright prerequisite by name."""

import json
from pathlib import Path

import pytest

import browser_support
from browser_support import APP, check_prerequisites, parse_version, satisfies


def fake_node(directory: Path, version: str) -> Path:
    """A stand-in `node` that reports `version` and prints $FAKE_CHROMIUM for `-e`."""
    directory.mkdir(parents=True, exist_ok=True)
    node = directory / "node"
    node.write_text(f'#!/bin/sh\nif [ "$1" = --version ]; then echo {version}; else printf %s "$FAKE_CHROMIUM"; fi\n')
    node.chmod(0o755)
    return node


def fake_app(root: Path, *, playwright: bool) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "package.json").write_text(json.dumps({"engines": {"node": "^20.19.0 || >=22.12.0"}}))
    if playwright:
        package = root / "node_modules/@playwright/test/package.json"
        package.parent.mkdir(parents=True)
        package.write_text("{}")
    return root


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("v16.20.2", False),
        ("v18.20.6", False),
        ("v20.18.9", False),
        ("v20.19.0", True),
        ("v21.7.3", False),
        ("v22.11.9", False),
        ("v22.12.0", True),
        ("v22.23.2", True),
        ("v24.19.0", True),
    ],
)
def test_engines_range_matches_mission_control_package(version, expected):
    engines = json.loads((APP / "package.json").read_text())["engines"]["node"]
    assert satisfies(parse_version(version), engines) is expected


def test_unsupported_engines_syntax_is_loud():
    with pytest.raises(ValueError, match="unsupported engines range"):
        satisfies((22, 0, 0), "~22.1.0")


def test_override_that_is_not_executable_names_the_variable(tmp_path):
    _, reason = check_prerequisites({"PANESTRIA_TEST_NODE": str(tmp_path / "missing"), "PATH": ""}, tmp_path)
    assert reason and "PANESTRIA_TEST_NODE=" in reason and "not an executable" in reason


def test_missing_node_on_path(tmp_path):
    _, reason = check_prerequisites({"PATH": str(tmp_path)}, tmp_path)
    assert reason and reason.startswith("node on PATH is not an executable")


def test_old_node_first_on_path_is_refused_with_the_required_range(tmp_path):
    fake_node(tmp_path / "bin", "v16.20.2")
    node, reason = check_prerequisites({"PATH": str(tmp_path / "bin")}, fake_app(tmp_path / "app", playwright=True))
    assert node is None
    assert reason and "v16.20.2" in reason and "^20.19.0 || >=22.12.0" in reason and "PANESTRIA_TEST_NODE" in reason


def test_override_wins_over_path_then_requires_playwright_package(tmp_path):
    fake_node(tmp_path / "old", "v16.20.2")
    supported = fake_node(tmp_path / "new", "v22.23.2")
    environ = {"PANESTRIA_TEST_NODE": str(supported), "PATH": str(tmp_path / "old")}
    _, reason = check_prerequisites(environ, fake_app(tmp_path / "app", playwright=False))
    assert reason and "@playwright/test is not installed" in reason and "npm ci" in reason


def test_missing_chromium_download_is_named(tmp_path):
    node = fake_node(tmp_path / "bin", "v22.23.2")
    environ = {"PANESTRIA_TEST_NODE": str(node), "FAKE_CHROMIUM": str(tmp_path / "absent/chrome")}
    _, reason = check_prerequisites(environ, fake_app(tmp_path / "app", playwright=True))
    assert reason and "Playwright Chromium is not installed" in reason and "playwright install chromium" in reason


def test_all_prerequisites_present_returns_the_resolved_node(tmp_path):
    node = fake_node(tmp_path / "bin", "v22.23.2")
    chrome = tmp_path / "chrome"
    chrome.write_text("")
    environ = {"PATH": str(tmp_path / "bin"), "FAKE_CHROMIUM": str(chrome)}
    assert check_prerequisites(environ, fake_app(tmp_path / "app", playwright=True)) == (str(node), None)


def test_missing_prerequisite_skips_locally_and_fails_in_ci(monkeypatch):
    monkeypatch.setattr(browser_support, "_session_prerequisites", lambda: (None, "node on PATH is v16.20.2"))
    monkeypatch.delenv("CI", raising=False)
    with pytest.raises(pytest.skip.Exception, match="requires_browser: node on PATH is v16.20.2"):
        browser_support.browser_node()
    monkeypatch.setenv("CI", "true")
    with pytest.raises(pytest.fail.Exception, match="requires_browser: node on PATH is v16.20.2"):
        browser_support.browser_node()
