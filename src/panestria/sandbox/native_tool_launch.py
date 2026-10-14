"""Container-only launcher for one reviewed script and a digest-bound data file."""

from __future__ import annotations

import hashlib
import json
import runpy
import sys
from pathlib import Path


def main() -> None:
    # All arguments come from the gateway, never from a worker command string.
    script = Path("/runtime/native-command.py")
    request = Path("/runtime/native-request.json")
    try:
        if len(sys.argv) != 3:
            raise ValueError
        if hashlib.sha256(script.read_bytes()).hexdigest() != sys.argv[1]:
            raise ValueError
        data = request.read_bytes()
        if len(data) > 64 * 1024 or hashlib.sha256(data).hexdigest() != sys.argv[2]:
            raise ValueError
        envelope = json.loads(data)
    except (OSError, ValueError):
        raise SystemExit("native_tool_input_mismatch") from None
    sys.argv = [str(script)]
    runpy.run_path(str(script), init_globals={"PANESTRIA_TOOL_REQUEST": envelope}, run_name="__main__")


if __name__ == "__main__":
    main()
