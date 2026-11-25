"""Read-only assets that ship with panestria, found the same way in a wheel or a checkout.

A built wheel carries each asset under ``panestria/_assets/`` and the Alembic
migrations under ``panestria/_migrations/`` (see
``[tool.hatch.build.targets.wheel.force-include]`` in ``pyproject.toml``). A
source checkout, including an editable install, reads the originals where the
repository keeps them. Consumers still verify each asset's pinned digest before
use, so this lookup grants no trust of its own.
"""

from __future__ import annotations

from pathlib import Path

SKILLS_ARCHIVE = "agentos-skills-v0.1.0.zip"

_PACKAGED = Path(__file__).resolve().parent / "_assets"
_CHECKOUT = Path(__file__).resolve().parents[2] / "docs/specification/attachments"
_PACKAGED_MIGRATIONS = Path(__file__).resolve().parent / "_migrations"
_CHECKOUT_MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
_PACKAGED_DASHBOARD = Path(__file__).resolve().parent / "_assets" / "mission-control"
_CHECKOUT_DASHBOARD = Path(__file__).resolve().parents[2] / "apps/mission-control/dist"


class AssetUnavailable(Exception):
    pass


def skills_archive() -> Path:
    """Return the pinned agentos-skills archive (hardware probe and worker skills)."""
    for candidate in (_PACKAGED / SKILLS_ARCHIVE, _CHECKOUT / SKILLS_ARCHIVE):
        if candidate.is_file():
            return candidate
    raise AssetUnavailable("packaged_asset_missing")


def migrations() -> Path:
    """Return the Alembic script directory (``env.py`` and ``versions/``) this package ships."""
    for candidate in (_PACKAGED_MIGRATIONS, _CHECKOUT_MIGRATIONS):
        if (candidate / "env.py").is_file() and (candidate / "versions").is_dir():
            return candidate
    raise AssetUnavailable("packaged_asset_missing")


def mission_control() -> Path:
    """Return the built Mission Control dashboard (``index.html`` and its assets).

    A wheel built without ``npm run build`` has none; hatch_build.py documents
    how a release build requires it.
    """
    for candidate in (_PACKAGED_DASHBOARD, _CHECKOUT_DASHBOARD):
        if (candidate / "index.html").is_file():
            return candidate
    raise AssetUnavailable("packaged_asset_missing")
