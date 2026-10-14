"""Load test-only stack helpers before integration/e2e collection."""

import subprocess
from collections.abc import Iterator

import pytest

from stack_support import COMPOSE, DATABASE_URL

# Importing from this directory also makes stack_support available when pytest
# collects only an e2e or integration node. Neither application imports this file.
assert "panestria-r0-tests-" in COMPOSE[-1] and ":55440/" in DATABASE_URL


@pytest.fixture(scope="session", autouse=True)
def _cleanup_regression_stack(request: pytest.FixtureRequest) -> Iterator[None]:
    uses_stack = any(getattr(item.module, "COMPOSE", None) == COMPOSE for item in request.session.items)
    try:
        yield
    finally:
        if uses_stack:
            subprocess.run([*COMPOSE, "down", "-v"], check=True, capture_output=True, timeout=30)
