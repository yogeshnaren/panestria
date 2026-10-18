"""Container-only python-memory-v1 launcher; no staged script or request files."""

from __future__ import annotations

import json
import runpy
import sys
from types import ModuleType


def main() -> None:
    # All arguments come from the gateway, never from a worker command string.
    protocol = runpy.run_path("/runtime/native-input.py")
    try:
        if len(sys.argv) != 3:
            raise ValueError
        frame = protocol["decode_frame"](sys.stdin.buffer, script_sha256=sys.argv[1], request_sha256=sys.argv[2])
        envelope = json.loads(frame.request)
        if not isinstance(envelope, dict):
            raise ValueError
    except (OSError, ValueError, protocol["InputFrameRejected"]):
        raise SystemExit("native_tool_input_mismatch") from None
    filename = "/virtual/panestria-command-" + sys.argv[1] + ".py"
    sys.argv = [filename]
    program = ModuleType("__main__")
    program.__dict__.update(
        {
            "__name__": "__main__",
            "__file__": filename,
            "__package__": None,
            "__spec__": None,
            "__loader__": None,
            "__cached__": None,
            "PANESTRIA_TOOL_REQUEST": envelope,
        }
    )
    previous = sys.modules.get("__main__")
    sys.modules["__main__"] = program
    try:
        exec(compile(frame.script, filename, "exec", dont_inherit=True), program.__dict__)
    finally:
        if previous is None:
            sys.modules.pop("__main__", None)
        else:
            sys.modules["__main__"] = previous


if __name__ == "__main__":
    main()
