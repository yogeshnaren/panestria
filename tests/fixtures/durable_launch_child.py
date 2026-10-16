"""Owned synthetic controller child for actual SIGKILL recovery tests; no native/model."""

import json
import sys
import time
from pathlib import Path

import psycopg

from panestria.contracts.native_tools import ToolScope
from panestria.execution.tool_authority import DurableToolAuthority
from panestria.kernel.goals import Actor
from panestria.sandbox.native_tool_gateway import ToolPermit
from panestria.sandbox.profiles import ReadOnlyMount, SandboxProfile


def main():
    data = json.loads(Path(sys.argv[1]).read_text())
    scope = ToolScope.model_validate_json(json.dumps(data["scope"]))
    permit = ToolPermit(
        scope,
        data["request_sha256"],
        data["registry_sha256"],
        Path(data["workspace"]),
        SandboxProfile(**data["profile"]),
        time.monotonic() + 10,
    )

    def connect():
        return psycopg.connect(data["dsn"], connect_timeout=1, options="-c statement_timeout=500 -c lock_timeout=500")

    authority = DurableToolAuthority(connect, Actor(data["owner"], data["project"]), data["invocation_id"])
    authority.claim(permit)
    runner = authority.runner_factory(permit)(
        Path(data["root"]), (ReadOnlyMount(Path(data["script"]), "/runtime/crash-check.py"),)
    )

    def barrier():
        Path(data["ready"]).write_text(data["phase"])
        while True:
            time.sleep(0.1)

    if data["phase"] == "intent":
        original = runner._on_launch

        def after_intent(reference, profile):
            original(reference, profile)
            barrier()

        runner._on_launch = after_intent
    elif data["phase"] == "created":
        original_start = runner._before_start

        def before_start():
            original_start()
            barrier()

        runner._before_start = before_start
    runner.run(permit.workspace, ("/usr/local/bin/python", "-I", "/runtime/crash-check.py"), permit.profile)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # No raw exception/DSN/task content enters the test's child diagnostics.
        print("synthetic_controller_failed:" + type(exc).__name__, file=sys.stderr)
        raise SystemExit(2) from None
