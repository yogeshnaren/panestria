"""Digest of the installed panestria source tree for runtime attestations."""

from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path

# Git's racy-clean rule: a file changed this close to the read can be rewritten
# again within one filesystem timestamp tick without a visible stat change.
_RACY_NANOSECONDS = 2_000_000_000
_Signature = tuple[tuple[str, int, int, int, int, int], ...]
_lock = threading.Lock()
_cache: dict[Path, tuple[_Signature, str]] = {}


def source_sha256(root: Path) -> str:
    """Return SHA-256 over every ``*.py`` under ``root``: relative path, NUL, bytes.

    Authority watchdogs evaluate runtime versions several times a second while
    a worker runs. Bytes are re-read whenever a file is added, removed or its
    size, mtime, ctime or inode changes, so any edit still changes the result
    without rehashing an unchanged tree on every observation.
    """
    paths = sorted(root.rglob("*.py"))
    stats = [path.stat() for path in paths]
    signature = tuple(
        (str(path.relative_to(root)), s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_ino, s.st_dev)
        for path, s in zip(paths, stats, strict=True)
    )
    with _lock:
        cached = _cache.get(root)
    if cached is not None and cached[0] == signature:
        return cached[1]
    started = time.time_ns()
    digest = hashlib.sha256()
    for (relative, *_), path in zip(signature, paths, strict=True):
        digest.update(relative.encode() + b"\0" + path.read_bytes())
    value = digest.hexdigest()
    if all(started - max(s.st_mtime_ns, s.st_ctime_ns) > _RACY_NANOSECONDS for s in stats):
        with _lock:
            _cache[root] = (signature, value)
    return value
