"""Node/Playwright prerequisites for the physical Mission Control browser journeys.

Each journey runs an `apps/mission-control/tests/*.mjs` script under Node with
@playwright/test and Playwright's Chromium. Tests marked `requires_browser` are
checked in `tests/conftest.py` before their fixtures start: a missing
prerequisite skips locally with the reason and fails in CI, which installs all
of them for the platform lane.
"""

from __future__ import annotations

import functools
import json
import os
import re
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "apps/mission-control"
NODE_OVERRIDE = "PANESTRIA_TEST_NODE"
CHROMIUM_INSTALL = "npx --no-install playwright install chromium"

Version = tuple[int, int, int]


def parse_version(text: str) -> Version:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?", text.strip())
    if match is None:
        raise ValueError(f"unparseable version {text!r}")
    return int(match[1]), int(match[2]), int(match[3])


def satisfies(version: Version, engines: str) -> bool:
    """Evaluate the `^X.Y.Z || >=X.Y.Z` form package.json engines uses (major >= 1)."""
    for alternative in (part.strip() for part in engines.split("||")):
        if alternative.startswith("^"):
            low = parse_version(alternative[1:])
            if low <= version < (low[0] + 1, 0, 0):
                return True
        elif alternative.startswith(">="):
            if version >= parse_version(alternative[2:]):
                return True
        else:
            raise ValueError(f"unsupported engines range {alternative!r}; extend tests/browser_support.py")
    return False


def check_prerequisites(environ: Mapping[str, str], app: Path = APP) -> tuple[str | None, str | None]:
    """Return `(node, None)` when the journeys can run, otherwise `(None, reason)`."""
    override = environ.get(NODE_OVERRIDE)
    source = f"{NODE_OVERRIDE}={override}" if override else "node on PATH"
    node = shutil.which(override or "node", path=environ.get("PATH"))
    if node is None:
        return None, f"{source} is not an executable; set {NODE_OVERRIDE} to a supported Node binary"
    engines = json.loads((app / "package.json").read_text())["engines"]["node"]
    try:
        reported = subprocess.run(
            [node, "--version"], capture_output=True, text=True, timeout=10, check=True
        ).stdout.strip()
        version = parse_version(reported)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        return None, f"{source} ({node}) did not report a Node version: {error}"
    if not satisfies(version, engines):
        return None, f"{source} ({node}) is {reported}; Mission Control requires Node {engines}. Set {NODE_OVERRIDE}"
    if not (app / "node_modules/@playwright/test/package.json").is_file():
        return None, f"@playwright/test is not installed; run `npm ci` in {app}"
    # executablePath() names where Playwright expects its Chromium (honouring
    # PLAYWRIGHT_BROWSERS_PATH) whether or not it has been downloaded.
    located = subprocess.run(
        [node, "-e", "process.stdout.write(require('@playwright/test').chromium.executablePath())"],
        cwd=app,
        env=dict(environ),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if located.returncode != 0:
        return None, f"@playwright/test did not load: {located.stderr.strip()[-300:]}"
    if not located.stdout or not Path(located.stdout).is_file():
        return None, f"Playwright Chromium is not installed at {located.stdout!r}; run `{CHROMIUM_INSTALL}` in {app}"
    return node, None


@functools.cache
def _session_prerequisites() -> tuple[str | None, str | None]:
    return check_prerequisites(os.environ)


def browser_node() -> str:
    """Return the checked Node binary; skip locally or fail in CI when a prerequisite is missing."""
    node, reason = _session_prerequisites()
    if node is None:
        message = f"requires_browser: {reason}"
        if os.environ.get("CI"):
            pytest.fail(message, pytrace=False)
        pytest.skip(message)
    return node
