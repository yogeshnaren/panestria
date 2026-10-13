"""A test-process-owned Compose project, separate port and project-scoped volume."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_DATABASE_PORT = 55440
COMPOSE = [
    "docker",
    "compose",
    "-f",
    str(ROOT / "tests/fixtures/compose.r0-tests.yaml"),
    "-p",
    f"panestria-r0-tests-{os.getpid()}",
]
DATABASE_URL = "postgresql://panestria_synthetic:placeholder-not-a-secret@127.0.0.1:55440/panestria_synthetic"
