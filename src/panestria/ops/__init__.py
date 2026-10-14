"""Scoped local PostgreSQL cleanup. This does not manage domain data."""

from __future__ import annotations

import shutil
import stat
from pathlib import Path

EXPECTED_VOLUME = "panestria_s3_pgdata"
LOOPBACK_BIND = "127.0.0.1"
HOST_PORT = 55432


class CleanupDenied(Exception):
    """Reset refused. The code is safe to print; paths are not."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def reset_volume_directory(volume_name: str, mount: Path) -> None:
    """Delete children of one expected data directory.

    A symlink mount or symlink child is refused before any deletion.
    """
    if volume_name != EXPECTED_VOLUME:
        raise CleanupDenied("wrong_volume")
    info = mount.lstat()
    if stat.S_ISLNK(info.st_mode):
        raise CleanupDenied("symlink_mount")
    if not stat.S_ISDIR(info.st_mode):
        raise CleanupDenied("not_a_directory")
    children = list(mount.iterdir())
    if any(child.is_symlink() for child in children):
        raise CleanupDenied("symlink_child")
    for child in children:
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
