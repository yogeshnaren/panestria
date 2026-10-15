"""Reviewed fixed-path writer. This file runs inside the secret-free container."""

import json
import os
from pathlib import Path

request = json.loads(Path("/runtime/native-request.json").read_text())
proposal = json.loads(request["payload_json"])
assert set(proposal) == {"path", "content"} and proposal["path"] == "calculator.py"
content = proposal["content"].encode()
assert 0 < len(content) <= 4096
fd = os.open("/workspace/calculator.py", os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW)
with os.fdopen(fd, "wb") as target:
    target.write(content)
print("candidate-applied")
