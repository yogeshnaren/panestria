"""The built wheel carries its assets and notices, and nothing from outside the package."""

from __future__ import annotations

import hashlib
import os
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

from panestria.assets import SKILLS_ARCHIVE
from panestria.resources.hardware import ZIP_SHA256

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    # Build the sdist, then the wheel from it (uv's default), so a file the
    # sdist forgets breaks this test instead of a user's install.
    out = tmp_path_factory.mktemp("dist")
    uv = Path(os.environ["UV"]) if "UV" in os.environ else Path("uv")
    subprocess.run([str(uv), "build", "--out-dir", str(out)], cwd=ROOT, check=True, capture_output=True, timeout=300)
    (wheel,) = out.glob("panestria-*.whl")
    (sdist,) = out.glob("panestria-*.tar.gz")
    return wheel, sdist


def test_the_wheel_ships_the_pinned_skills_archive_and_notices(built: tuple[Path, Path]) -> None:
    with zipfile.ZipFile(built[0]) as wheel:
        names = set(wheel.namelist())
        archive = wheel.read(f"panestria/_assets/{SKILLS_ARCHIVE}")
        (metadata,) = [n for n in names if n.endswith(".dist-info/METADATA")]
        info = metadata.rsplit("/", 1)[0]
        text = wheel.read(metadata).decode()
    assert hashlib.sha256(archive).hexdigest() == ZIP_SHA256
    assert {
        f"{info}/licenses/LICENSE",
        f"{info}/licenses/NOTICE",
        f"{info}/licenses/third_party/agentos-skills/LICENSE",
    } <= names
    assert "License-Expression: MIT" in text
    assert "Classifier: Operating System :: POSIX :: Linux" in text


def test_the_wheel_ships_every_migration_and_the_downgrade_guard(built: tuple[Path, Path]) -> None:
    with zipfile.ZipFile(built[0]) as wheel:
        shipped = {
            n.removeprefix("panestria/_migrations/") for n in wheel.namelist() if n.startswith("panestria/_migrations/")
        }
    tracked = {
        str(path.relative_to(ROOT / "migrations"))
        for path in (ROOT / "migrations").rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    assert {"env.py", "downgrade_guard.py", "alembic.ini"} <= shipped
    assert shipped == tracked


def test_the_wheel_holds_only_the_package_and_its_metadata(built: tuple[Path, Path]) -> None:
    with zipfile.ZipFile(built[0]) as wheel:
        names = wheel.namelist()
    tops = {name.split("/", 1)[0] for name in names}
    assert {top for top in tops if not top.endswith(".dist-info")} == {"panestria"}
    assert not [name for name in names if name.endswith((".pyc", ".pyo")) or "/__pycache__/" in name]


def test_the_sdist_carries_sources_and_assets_but_not_docs_tests_or_evidence(built: tuple[Path, Path]) -> None:
    with tarfile.open(built[1]) as sdist:
        members = {member.name.split("/", 1)[1] for member in sdist.getmembers() if "/" in member.name}
    assert f"docs/specification/attachments/{SKILLS_ARCHIVE}" in members
    assert {
        "LICENSE",
        "NOTICE",
        "README.md",
        "pyproject.toml",
        "src/panestria/assets.py",
        "migrations/env.py",
    } <= members
    assert not [name for name in members if name.startswith(("tests/", "evidence/", "apps/", "docs/project/"))]
