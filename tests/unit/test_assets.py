"""Packaged assets resolve in a wheel or a checkout and keep one pinned digest."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from panestria import assets
from panestria.brokers.harness.cli_profile import ARCHIVE_SHA256
from panestria.resources.hardware import ZIP_SHA256

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = ROOT / "docs/specification/attachments" / assets.SKILLS_ARCHIVE


def test_every_pin_of_the_skills_archive_agrees_with_the_recorded_attachment() -> None:
    recorded = (ROOT / "docs/specification/attachments/agentos-skills-v0.1.0.zip.sha256").read_text().split()[0]
    assert ARCHIVE_SHA256 == ZIP_SHA256 == recorded == hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()


def test_a_checkout_resolves_the_original_attachment() -> None:
    assert assets.skills_archive() == ORIGINAL


def test_the_packaged_copy_wins_over_a_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    packaged = tmp_path / "_assets"
    packaged.mkdir()
    (packaged / assets.SKILLS_ARCHIVE).write_bytes(ORIGINAL.read_bytes())
    monkeypatch.setattr(assets, "_PACKAGED", packaged)
    assert assets.skills_archive() == packaged / assets.SKILLS_ARCHIVE


def test_a_missing_asset_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(assets, "_PACKAGED", tmp_path / "wheel")
    monkeypatch.setattr(assets, "_CHECKOUT", tmp_path / "checkout")
    with pytest.raises(assets.AssetUnavailable, match="^packaged_asset_missing$"):
        assets.skills_archive()


def test_migrations_resolve_from_the_checkout_and_prefer_a_packaged_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert assets.migrations() == ROOT / "migrations"
    packaged = tmp_path / "_migrations"
    (packaged / "versions").mkdir(parents=True)
    (packaged / "env.py").write_text("")
    monkeypatch.setattr(assets, "_PACKAGED_MIGRATIONS", packaged)
    assert assets.migrations() == packaged
    monkeypatch.setattr(assets, "_PACKAGED_MIGRATIONS", tmp_path / "missing")
    monkeypatch.setattr(assets, "_CHECKOUT_MIGRATIONS", tmp_path / "also-missing")
    with pytest.raises(assets.AssetUnavailable, match="^packaged_asset_missing$"):
        assets.migrations()
