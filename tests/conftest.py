"""Load test-only stack helpers before integration/e2e collection."""

import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from hypothesis import HealthCheck, settings

from stack_support import COMPOSE, DATABASE_URL, TEST_DATABASE_PORT

# Importing from this directory also makes stack_support available when pytest
# collects only an e2e or integration node. Neither application imports this file.
assert "panestria-r0-tests-" in COMPOSE[-1] and f":{TEST_DATABASE_PORT}/" in DATABASE_URL

# Subprocesses that run `uv` or `make` must use the same pinned uv that started
# this test session (`uv run` exports UV), not whatever uv is first on PATH.
if os.environ.get("UV"):
    os.environ["PATH"] = f"{Path(os.environ['UV']).parent}{os.pathsep}{os.environ.get('PATH', '')}"

# Property tests: deterministic in CI (reproducible failures), deeper nightly.
settings.register_profile("ci", derandomize=True, max_examples=100, deadline=None)
settings.register_profile("nightly", max_examples=2000, deadline=None, suppress_health_check=[HealthCheck.too_slow])
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "ci"))

_LAYER_MARKERS = {"unit": "unit", "contract": "contract"}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark unit/contract tests by directory so `-m unit` selects the whole lane."""
    for item in items:
        layer = _LAYER_MARKERS.get(Path(str(item.fspath)).parent.name)
        if layer and not item.get_closest_marker(layer):
            item.add_marker(layer)


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Skip non-root-only tests locally as root; never let CI skip them silently."""
    nonroot = item.get_closest_marker("requires_nonroot") or item.get_closest_marker("docker_boundary")
    if nonroot and os.geteuid() == 0:
        if os.environ.get("CI"):
            pytest.fail("requires_nonroot test cannot run as root in CI", pytrace=False)
        pytest.skip("requires_nonroot: the product refuses euid 0; run as a normal user")


@pytest.fixture(scope="session", autouse=True)
def _cleanup_regression_stack(request: pytest.FixtureRequest) -> Iterator[None]:
    uses_stack = any(getattr(item.module, "COMPOSE", None) == COMPOSE for item in request.session.items)
    try:
        yield
    finally:
        if uses_stack:
            subprocess.run([*COMPOSE, "down", "-v"], check=True, capture_output=True, timeout=30)
