"""Test-only pause. Unset the variable and this is a no-op, including on replay."""

from __future__ import annotations

import os
import time
from pathlib import Path


def crash_gate(point: str) -> None:
    if os.environ.get("PANESTRIA_CRASH_AT") != point:
        return
    Path(os.environ["PANESTRIA_READY_FILE"]).write_text(point)
    while True:
        time.sleep(0.2)
