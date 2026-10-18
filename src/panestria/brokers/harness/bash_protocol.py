"""Distinct edit-capable MCP profile reusing the bounded private wire lifecycle."""

from typing import Any

from panestria.brokers.harness.command_protocol import CheckExecutor, RegisteredCheckSession
from panestria.contracts.native_build import MAX_BASH_BYTES, bash_script


class ScopedBashSession(RegisteredCheckSession):
    server_name = "panestria-scoped-bash"

    def __init__(self, job_ref: str, executor: CheckExecutor) -> None:
        # V1 deliberately permits one command per durable worker job. Reopening
        # the transport does not reset the controller's committed dispatch fence.
        super().__init__(("scoped-bash",), job_ref, executor, max_calls=1)

    def _tool_list(self) -> dict[str, Any]:
        return {
            "tools": [
                {
                    "name": "run_scoped_bash",
                    "description": (
                        "Run one bounded Bash script in the job's network-disabled disposable workspace. "
                        "Return execution metadata, not independent acceptance. No host shell or credentials."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "job_ref": {"type": "string", "const": self._candidate},
                            "script": {"type": "string", "minLength": 1, "maxLength": MAX_BASH_BYTES},
                        },
                        "required": ["job_ref", "script"],
                        "additionalProperties": False,
                    },
                    "annotations": {
                        "readOnlyHint": False,
                        "destructiveHint": True,
                        "idempotentHint": False,
                        "openWorldHint": False,
                    },
                }
            ]
        }

    def _command(self, params: dict[str, Any]) -> str:
        args = params.get("arguments")
        if (
            params.get("name") != "run_scoped_bash"
            or not isinstance(args, dict)
            or set(args) != {"job_ref", "script"}
            or args["job_ref"] != self._candidate
        ):
            raise ValueError
        return bash_script(args["script"])
