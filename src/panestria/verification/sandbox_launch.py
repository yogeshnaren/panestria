"""Standalone trusted verifier launcher; the bundle is readonly inside the sandbox."""

from __future__ import annotations

import hashlib
import os
import runpy
import sys
from pathlib import Path

script, expected = Path(sys.argv[1]), sys.argv[2]
if script.parent != Path("/runtime/checks") or hashlib.sha256(script.read_bytes()).hexdigest() != expected:
    raise SystemExit(125)
os.environ["PANESTRIA_CANDIDATE"] = "/workspace"
sys.argv = [str(script)]
runpy.run_path(str(script), run_name="__main__")
