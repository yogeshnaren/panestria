"""Read-only assets that ship with panestria, found the same way in a wheel or a checkout.

A built wheel carries each asset under ``panestria/_assets/`` (see
``[tool.hatch.build.targets.wheel.force-include]`` in ``pyproject.toml``). A
source checkout, including an editable install, reads the original file where
the repository keeps it. Consumers still verify each asset's pinned digest
before use, so this lookup grants no trust of its own.
"""

from __future__ import annotations

from pathlib import Path

SKILLS_ARCHIVE = "agentos-skills-v0.1.0.zip"

_PACKAGED = Path(__file__).resolve().parent / "_assets"
_CHECKOUT = Path(__file__).resolve().parents[2] / "docs/specification/attachments"


class AssetUnavailable(Exception):
    pass


def skills_archive() -> Path:
    """Return the pinned agentos-skills archive (hardware probe and worker skills)."""
    for candidate in (_PACKAGED / SKILLS_ARCHIVE, _CHECKOUT / SKILLS_ARCHIVE):
        if candidate.is_file():
            return candidate
    raise AssetUnavailable("packaged_asset_missing")
