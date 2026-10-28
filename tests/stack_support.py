"""A test-process-owned Compose project, separate port and project-scoped volume."""

from __future__ import annotations

import os
import socket
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    """Return a currently unused loopback TCP port chosen by the kernel."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


# One disposable port per test process (override with R0_TEST_DATABASE_PORT).
# Deliberately not PANESTRIA_*: Settings rejects unknown variables with that prefix.
# Exported so every `docker compose` child publishes the same port.
TEST_DATABASE_PORT = int(os.environ.get("R0_TEST_DATABASE_PORT") or free_port())
os.environ["R0_TEST_DATABASE_PORT"] = str(TEST_DATABASE_PORT)
COMPOSE = [
    "docker",
    "compose",
    "-f",
    str(ROOT / "tests/fixtures/compose.r0-tests.yaml"),
    "-p",
    f"panestria-r0-tests-{os.getpid()}",
]
DATABASE_URL = (
    f"postgresql://panestria_synthetic:placeholder-not-a-secret@127.0.0.1:{TEST_DATABASE_PORT}/panestria_synthetic"
)
