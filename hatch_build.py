"""Hatch build hook: ship the built Mission Control dashboard when it has been built.

``apps/mission-control/dist`` is a build output (``npm run build``), not tracked
source. When it exists, the wheel carries it as ``panestria/_assets/mission-control``
and the sdist carries it at its own path, so a wheel built from the sdist has it
too. A development build without it still succeeds, without the dashboard. A
release or install-smoke build sets ``WHEEL_REQUIRE_DASHBOARD=1`` so a
missing dashboard fails the build instead of shipping a wheel without one. The
name deliberately lacks the ``PANESTRIA_`` prefix, because the settings loader
rejects unknown variables with that prefix.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

DIST = "apps/mission-control/dist"
REQUIRE = "WHEEL_REQUIRE_DASHBOARD"


class CustomBuildHook(BuildHookInterface):  # type: ignore[type-arg]
    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        dist = Path(self.root) / DIST
        if not (dist / "index.html").is_file():
            if os.environ.get(REQUIRE) == "1":
                raise RuntimeError(f"{REQUIRE}=1, but {DIST}/index.html is missing: run `npm run build` there first")
            return
        target = "panestria/_assets/mission-control" if self.target_name == "wheel" else DIST
        build_data["force_include"][str(dist)] = target
