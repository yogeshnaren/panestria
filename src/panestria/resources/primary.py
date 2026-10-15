"""One owner-managed primary model per host, including across API process restarts."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path

from panestria.contracts.inference import InferenceUnavailable


class PrimaryLease:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.descriptor: int | None = None

    def acquire(self) -> None:
        if self.descriptor is not None:
            raise InferenceUnavailable("primary_already_owned")
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.directory.stat()
        if self.directory.is_symlink() or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise InferenceUnavailable("primary_lock_directory_not_private")
        descriptor = os.open(self.directory / "primary.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        info = os.fstat(descriptor)
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            os.close(descriptor)
            raise InferenceUnavailable("primary_lock_not_private")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(descriptor)
            raise InferenceUnavailable("primary_in_use") from None
        self.descriptor = descriptor

    def release(self) -> None:
        if self.descriptor is not None:
            os.close(self.descriptor)
            self.descriptor = None
