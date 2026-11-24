"""Owner-private local state: private directories, atomic JSON writes and run locks.

Product state stores (owner Build, native plans, qualification journals,
background runs, build metrics) share these helpers. They import only the
standard library, so any layer may use them.
"""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class LocalStateUnavailable(Exception):
    """A private state directory or run lock cannot be used safely.

    The codes predate this module and are kept unchanged for compatibility:
    ``unsafe_demo_root``, ``private_demo_root_required`` and
    ``demo_operation_running``.
    """


def private_dir(path: Path) -> Path:
    """Create ``path`` 0700 if missing; require it resolved, owner-owned and private."""
    if path.is_symlink():
        raise LocalStateUnavailable("unsafe_demo_root")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.resolve() != path or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise LocalStateUnavailable("private_demo_root_required")
    return path


def atomic_write_json(path: Path, body: object) -> None:
    """Replace ``path`` with ``body`` as sorted-key JSON, fsynced, via a sibling temp file."""
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(body, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


@contextmanager
def exclusive_lock(path: Path) -> Iterator[None]:
    """Hold a non-blocking exclusive ``flock`` on ``path``; refuse if another holder exists."""
    with path.open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LocalStateUnavailable("demo_operation_running") from None
        yield
