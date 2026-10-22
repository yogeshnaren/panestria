"""Cached hashes of public trusted runtime artifacts, never private content."""

import hashlib
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=4096)
def _file_hash(path: str, identity: tuple[int, ...]) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def artifact_hash(path: Path) -> str:
    info = path.stat()
    if not path.is_file():
        raise ValueError("runtime_artifact_unavailable")
    # Inode/size/mtime/ctime changes invalidate cached public bytes.
    return _file_hash(str(path), (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns))
