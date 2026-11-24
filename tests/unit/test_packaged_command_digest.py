"""Packaged command scripts are trusted by a code-pinned digest, not install mode.

These tests read bytes only; they do not launch a sandbox or authorize a tool.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

import pytest

from panestria.sandbox import native_tool_gateway
from panestria.sandbox.native_tool_gateway import (
    SCOPED_BASH_SCRIPT,
    SCOPED_BASH_SHA256,
    GatewayRejected,
    ReviewedCommand,
    _script_bytes,
)


def _packaged_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: int) -> tuple[Path, Path]:
    """Stand a copy of the real packaged bytes in for the installed path."""
    root = (tmp_path / "attempts").resolve()
    root.mkdir()
    installed = (tmp_path / "site-packages" / "scoped_bash.py").resolve()
    installed.parent.mkdir()
    shutil.copyfile(SCOPED_BASH_SCRIPT, installed)
    installed.chmod(mode)
    monkeypatch.setattr(native_tool_gateway, "_PACKAGED_SCRIPTS", {installed: SCOPED_BASH_SHA256})
    return root, installed


def _command(script: Path, sha256: str = SCOPED_BASH_SHA256) -> ReviewedCommand:
    return ReviewedCommand("scoped-bash", script, sha256, "edit")


def test_pinned_digest_matches_the_packaged_scoped_bash_bytes() -> None:
    assert SCOPED_BASH_SCRIPT.is_absolute()
    assert SCOPED_BASH_SCRIPT.resolve() == SCOPED_BASH_SCRIPT
    assert SCOPED_BASH_SCRIPT == Path(native_tool_gateway.__file__).resolve().with_name("scoped_bash.py")
    assert hashlib.sha256(SCOPED_BASH_SCRIPT.read_bytes()).hexdigest() == SCOPED_BASH_SHA256
    assert native_tool_gateway._PACKAGED_SCRIPTS == {SCOPED_BASH_SCRIPT: SCOPED_BASH_SHA256}


def test_installed_scoped_bash_is_accepted_whatever_its_install_mode(tmp_path: Path) -> None:
    # The real installed file, as left by this checkout's umask or installer.
    data = _script_bytes(_command(SCOPED_BASH_SCRIPT), (tmp_path / "attempts").resolve())
    assert hashlib.sha256(data).hexdigest() == SCOPED_BASH_SHA256


@pytest.mark.parametrize("install", ["group-writable", "world-writable", "hardlinked"])
def test_packaged_script_with_pinned_digest_is_accepted_under_loose_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, install: str
) -> None:
    mode = {"group-writable": 0o664, "world-writable": 0o666, "hardlinked": 0o644}[install]
    root, installed = _packaged_copy(tmp_path, monkeypatch, mode)
    if install == "hardlinked":
        # Package managers may hard-link installed files from a shared cache.
        os.link(installed, tmp_path / "cache-entry.py")
    assert _script_bytes(_command(installed), root) == SCOPED_BASH_SCRIPT.read_bytes()


@pytest.mark.parametrize("change", ["appended", "replaced"])
def test_tampered_packaged_script_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str) -> None:
    root, installed = _packaged_copy(tmp_path, monkeypatch, 0o664)
    if change == "appended":
        with installed.open("ab") as stream:
            stream.write(b"\nimport subprocess\n")
    else:
        installed.write_bytes(b"print('unreviewed')\n")
    with pytest.raises(GatewayRejected, match="command_digest_mismatch"):
        _script_bytes(_command(installed), root)


def test_packaged_path_bound_to_another_digest_keeps_strict_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, installed = _packaged_copy(tmp_path, monkeypatch, 0o664)
    installed.write_bytes(b"print('other reviewed bytes')\n")
    installed.chmod(0o664)
    other = hashlib.sha256(installed.read_bytes()).hexdigest()
    with pytest.raises(GatewayRejected, match="unsafe_command_script"):
        _script_bytes(_command(installed, other), root)


@pytest.mark.parametrize("bytes_from", ["own", "packaged"])
def test_owner_supplied_writable_script_stays_refused(tmp_path: Path, bytes_from: str) -> None:
    # Pinned trust follows the installed path, never a digest match elsewhere.
    root = (tmp_path / "attempts").resolve()
    root.mkdir()
    script = (tmp_path / "check.py").resolve()
    if bytes_from == "own":
        script.write_bytes(b"print('owner check')\n")
    else:
        shutil.copyfile(SCOPED_BASH_SCRIPT, script)
    script.chmod(0o664)
    digest = hashlib.sha256(script.read_bytes()).hexdigest()
    with pytest.raises(GatewayRejected, match="unsafe_command_script"):
        _script_bytes(ReviewedCommand("owner-check", script, digest, "read"), root)
    script.chmod(0o600)
    assert hashlib.sha256(_script_bytes(ReviewedCommand("owner-check", script, digest, "read"), root)).hexdigest() == (
        digest
    )


@pytest.mark.parametrize("change", ["symlink", "directory", "empty", "workspace"])
def test_packaged_path_keeps_link_type_size_and_root_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    root, installed = _packaged_copy(tmp_path, monkeypatch, 0o644)
    if change == "symlink":
        original = installed.with_suffix(".original")
        installed.rename(original)
        installed.symlink_to(original)
        reason = "unreviewed_script_path"
    elif change == "directory":
        installed.unlink()
        installed.mkdir()
        reason = "unsafe_command_script"
    elif change == "empty":
        installed.write_bytes(b"")
        reason = "unsafe_command_script"
    else:
        # A workspace-rooted path is never trusted, even with pinned bytes.
        moved = root / "scoped_bash.py"
        shutil.copyfile(installed, moved)
        monkeypatch.setattr(native_tool_gateway, "_PACKAGED_SCRIPTS", {moved: SCOPED_BASH_SHA256})
        installed = moved
        reason = "unreviewed_script_path"
    with pytest.raises(GatewayRejected, match=reason):
        _script_bytes(_command(installed), root)
