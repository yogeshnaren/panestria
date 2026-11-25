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


def test_the_wheel_holds_only_the_package_and_its_metadata(built: tuple[Path, Path]) -> None:
    with zipfile.ZipFile(built[0]) as wheel:
        names = wheel.namelist()
    tops = {name.split("/", 1)[0] for name in names}
    assert {top for top in tops if not top.endswith(".dist-info")} == {"panestria"}
    assert not [name for name in names if name.endswith((".pyc", ".pyo")) or "/__pycache__/" in name]


def test_the_wheel_contains_no_demo_or_synthetic_journey_code(built: tuple[Path, Path]) -> None:
    # The R0 demo, synthetic journey and proposal demo live in devkit/ (plan 1.8).
    with zipfile.ZipFile(built[0]) as wheel:
        names = wheel.namelist()
    markers = ("demo", "synthetic_journey")
    found = [name for name in names if any(marker in part for part in name.split("/") for marker in markers)]
    assert found == []
    assert not {"panestria/review.py", "panestria/brokers/harness/mock.py"} & set(names)
    assert not [name for name in names if "panestria_devkit" in name]


def test_the_sdist_carries_sources_and_assets_but_not_docs_tests_or_evidence(built: tuple[Path, Path]) -> None:
    with tarfile.open(built[1]) as sdist:
        members = {member.name.split("/", 1)[1] for member in sdist.getmembers() if "/" in member.name}
    assert f"docs/specification/attachments/{SKILLS_ARCHIVE}" in members
    assert {"LICENSE", "NOTICE", "README.md", "pyproject.toml", "src/panestria/assets.py"} <= members
    assert not [name for name in members if name.startswith(("tests/", "evidence/", "apps/", "docs/project/", "devkit/"))]
