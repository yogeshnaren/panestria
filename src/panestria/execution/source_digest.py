"""Digest of the installed panestria source tree for runtime attestations."""

from __future__ import annotations

import hashlib
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

# Git's racy-clean rule: a file changed this close to the read can be rewritten
# again within one filesystem timestamp tick without a visible stat change.
_RACY_NANOSECONDS = 2_000_000_000
_StatKey = tuple[int, int, int, int, int]


@dataclass(frozen=True)
class _Snapshot:
    directories: tuple[tuple[str, _StatKey], ...]
    files: tuple[tuple[str, str, _StatKey], ...]
    sha256: str


_lock = threading.Lock()
_cache: dict[Path, _Snapshot] = {}


def _key(info: os.stat_result) -> _StatKey:
    return (info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_ino, info.st_dev)


def _unchanged(snapshot: _Snapshot) -> bool:
    # An added, removed or renamed entry changes its directory's mtime/ctime;
    # an edit changes the file's own stat. Either one forces a full rescan.
    try:
        return all(_key(os.stat(name)) == key for name, key in snapshot.directories) and all(
            _key(os.stat(name)) == key for name, _, key in snapshot.files
        )
    except OSError:
        return False


def source_sha256(root: Path) -> str:
    """Return SHA-256 over every ``*.py`` under ``root``: relative path, NUL, bytes.

    Authority watchdogs evaluate runtime versions several times a second while
    a worker runs. A cached result is reused only while every directory and
    file keeps its size, mtime, ctime and inode, so any edit, addition or
    removal is rehashed without walking or rehashing an unchanged tree.
    """
    with _lock:
        cached = _cache.get(root)
    if cached is not None and _unchanged(cached):
        return cached.sha256
    started = time.time_ns()
    directories = tuple((name, _key(os.stat(name))) for name, _, _ in os.walk(root))
    paths = sorted(root.rglob("*.py"))
    # rglob yields root/<relative>; slicing the prefix matches relative_to().
    prefix = len(os.path.join(str(root), ""))
    files = tuple((str(path), str(path)[prefix:], _key(path.stat())) for path in paths)
    digest = hashlib.sha256()
    for name, relative, _ in files:
        digest.update(relative.encode() + b"\0" + Path(name).read_bytes())
    snapshot = _Snapshot(directories, files, digest.hexdigest())
    stamps = [key for _, key in directories] + [key for _, _, key in files]
    if all(started - max(key[1], key[2]) > _RACY_NANOSECONDS for key in stamps):
        with _lock:
            _cache[root] = snapshot
    return snapshot.sha256
