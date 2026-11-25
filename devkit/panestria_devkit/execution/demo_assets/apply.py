"""Reviewed fixed-path writer. This file runs inside the secret-free container."""

import json
import os

# Bound by the explicit python-memory-v1 reviewed-command interface.
request: dict[str, str] = globals()["PANESTRIA_TOOL_REQUEST"]
proposal = json.loads(request["payload_json"])
assert set(proposal) == {"path", "content"} and proposal["path"] == "calculator.py"
content = proposal["content"].encode()
assert 0 < len(content) <= 4096
fd = os.open("/workspace/calculator.py", os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW)
with os.fdopen(fd, "wb") as target:
    target.write(content)
print("candidate-applied")
