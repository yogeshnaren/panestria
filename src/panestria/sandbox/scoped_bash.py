"""Reviewed container-only bridge. Loaded in memory by native_tool_launch.py.

The host sends a script as framed data to the existing non-root, secret-free,
network-none/seccomp sandbox. This module must never be a host shell executor.
"""

import os
from typing import Any


def main(request: dict[str, Any]) -> None:
    payload = request.get("payload_json")
    # The frame loader already decoded the outer ToolRequest; this value is the
    # canonical JSON string bound by the durable invocation's request digest.
    import json

    if type(payload) is not str:
        raise ValueError("invalid_scoped_bash_frame")
    body = json.loads(payload)
    script = body.get("script")
    if (
        set(body) != {"job_ref", "script"}
        or type(script) is not str
        or not script.strip()
        or "\0" in script
        or len(script.encode()) > 16 * 1024
        or os.getcwd() != "/workspace"
    ):
        raise ValueError("invalid_scoped_bash_frame")
    os.execve(
        "/bin/bash",
        ("bash", "--noprofile", "--norc", "-c", script, "panestria-worker"),
        {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp", "LANG": "C.UTF-8", "TMPDIR": "/tmp"},
    )


if __name__ == "__main__":
    main(PANESTRIA_TOOL_REQUEST)  # type: ignore[name-defined]  # noqa: F821
