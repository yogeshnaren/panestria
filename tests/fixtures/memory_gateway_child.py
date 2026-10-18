"""Own synthetic controller runs the real memory-input gateway before SIGKILL."""

import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path

import psycopg

from panestria.contracts.native_tools import ToolRequest, ToolScope
from panestria.execution.tool_authority import DurableToolAuthority
from panestria.kernel.goals import Actor
from panestria.sandbox.native_tool_gateway import NativeCommandRegistry, NativeToolGateway, ReviewedCommand, ToolPermit
from panestria.sandbox.profiles import SandboxProfile


def main():
    data = json.loads(Path(sys.argv[1]).read_text())
    script = Path(data["script"])
    registry = NativeCommandRegistry(
        (ReviewedCommand("memory-crash-check", script, hashlib.sha256(script.read_bytes()).hexdigest(), "edit"),)
    )
    request = ToolRequest.model_validate_json(json.dumps(data["request"]))
    permit = ToolPermit(
        ToolScope.model_validate_json(json.dumps(data["scope"])),
        request.sha256(),
        registry.sha256(),
        Path(data["workspace"]),
        SandboxProfile(**data["profile"]),
        time.monotonic() + 15,
    )

    def connect():
        return psycopg.connect(data["dsn"], connect_timeout=1, options="-c statement_timeout=500 -c lock_timeout=500")

    def forbidden(*args, **kwargs):
        raise AssertionError("memory gateway must allocate no host input stage")

    tempfile.TemporaryDirectory = forbidden
    targets = []

    def barrier():
        Path(data["ready"]).write_text(json.dumps({"phase": data["phase"], "mounts": targets}))
        while True:
            time.sleep(0.1)

    class Authority(DurableToolAuthority):
        def claim(self, permit):
            super().claim(permit)
            if data["phase"] == "claim":
                barrier()

        def runner_factory(self, permit):
            bound = super().runner_factory(permit)

            def make(root, mounts):
                targets.extend(m.destination for m in mounts)
                assert set(targets) == {"/runtime/native-launch.py", "/runtime/native-input.py"}
                runner = bound(root, mounts)
                if data["phase"] == "intent":
                    original = runner._on_launch

                    def intent(reference, profile):
                        original(reference, profile)
                        barrier()

                    runner._on_launch = intent
                elif data["phase"] == "created":
                    original_start = runner._before_start

                    def start():
                        original_start()
                        barrier()

                    runner._before_start = start
                return runner

            return make

    authority = Authority(connect, Actor(data["owner"], data["project"]), data["invocation_id"])
    # No explicit runner override: actual durable factory capability must be used.
    NativeToolGateway(Path(data["root"]), registry, authority).execute(request, permit)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("synthetic_memory_gateway_failed:" + type(exc).__name__, file=sys.stderr)
        raise SystemExit(2) from None
