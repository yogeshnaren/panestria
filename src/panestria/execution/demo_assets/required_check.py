"""Controller-owned tests. The candidate has a read-only mount."""

import os
from pathlib import Path
from typing import Any

source = Path(os.environ["PANESTRIA_CANDIDATE"], "calculator.py").read_text()
namespace: dict[str, Any] = {}
exec(compile(source, "calculator.py", "exec"), namespace)
assert set(namespace) == {"__builtins__", "add"}
for a, b in [(2, 3), (-2, -3), (-2, 3), (0, 0), (0, 9), (10**50, 10**50)]:
    assert namespace["add"](a, b) == a + b, (a, b)
print("6 independent calculator cases passed")
