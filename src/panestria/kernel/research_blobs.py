"""Bounded protected plaintext bytes, not fetch, classification or citation authority."""

from __future__ import annotations

import fcntl
import hashlib
import os
import re
import stat
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Self
from uuid import UUID

from panestria.contracts.research import MAX_SOURCE_BYTES
from panestria.kernel.goals import Actor

_LOCK_SECONDS = 5.0


class ResearchBlobUnavailable(ValueError):
    pass


@dataclass(frozen=True)
class ResearchBlobReceipt:
    sha256: str
    size_bytes: int


def _canonical_id(value: str) -> str:
    try:
        if type(value) is not str or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, AttributeError):
        raise ResearchBlobUnavailable("invalid_research_scope") from None
    return value


def _private_directory(fd: int) -> None:
    info = os.fstat(fd)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ResearchBlobUnavailable("unsafe_research_directory")


def _child(parent: int, name: str) -> int:
    try:
        os.mkdir(name, mode=0o700, dir_fd=parent)
    except FileExistsError:
        pass
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
    try:
        _private_directory(fd)
        os.fsync(parent)
    except BaseException:
        os.close(fd)
        raise
    return fd


class ResearchBlobStore:
    """Trusted controller only. Callers must separately validate artifact and fetch provenance."""

    def __init__(self, root: Path, actor: Actor) -> None:
        owner, project = _canonical_id(actor.owner_id), _canonical_id(actor.project_id)
        self._mutex = threading.RLock()
        self._fd = -1
        root_fd = owner_fd = -1
        try:
            if not root.is_absolute() or root.resolve(strict=True) != root:
                raise ResearchBlobUnavailable("unsafe_research_directory")
            root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            _private_directory(root_fd)
            owner_fd = _child(root_fd, owner)
            self._fd = _child(owner_fd, project)
        except (OSError, RuntimeError):
            raise ResearchBlobUnavailable("research_directory_unavailable") from None
        finally:
            for fd in (owner_fd, root_fd):
                if fd >= 0:
                    os.close(fd)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        with self._mutex:
            if self._fd >= 0:
                os.close(self._fd)
                self._fd = -1

    @contextmanager
    def _locked(self) -> Iterator[None]:
        deadline = time.monotonic() + _LOCK_SECONDS
        if not self._mutex.acquire(timeout=_LOCK_SECONDS):
            raise ResearchBlobUnavailable("research_store_busy")
        try:
            if self._fd < 0:
                raise ResearchBlobUnavailable("research_store_closed")
            try:
                _private_directory(self._fd)
                while True:
                    try:
                        fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise ResearchBlobUnavailable("research_store_busy") from None
                        time.sleep(min(0.01, remaining))
                try:
                    yield
                finally:
                    fcntl.flock(self._fd, fcntl.LOCK_UN)
            except OSError:
                raise ResearchBlobUnavailable("research_blob_io_unavailable") from None
        finally:
            self._mutex.release()

    def _file(self, name: str, links: tuple[int, ...], modes: tuple[int, ...]) -> tuple[bytes, os.stat_result]:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=self._fd)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.getuid()
                or before.st_nlink not in links
                or stat.S_IMODE(before.st_mode) not in modes
                or before.st_size > MAX_SOURCE_BYTES
            ):
                raise ResearchBlobUnavailable("unsafe_research_blob")
            raw = stream.read(MAX_SOURCE_BYTES + 1)
            after = os.fstat(stream.fileno())
            if (
                len(raw) > MAX_SOURCE_BYTES
                or len(raw) != before.st_size
                or (before.st_mode, before.st_uid, before.st_gid, before.st_nlink, before.st_size)
                != (after.st_mode, after.st_uid, after.st_gid, after.st_nlink, after.st_size)
                or before.st_mtime_ns != after.st_mtime_ns
                or before.st_ctime_ns != after.st_ctime_ns
            ):
                raise ResearchBlobUnavailable("research_blob_changed")
            return raw, after

    def _read(self, digest: str, expected_size: int) -> bytes:
        raw, _ = self._file(digest, (1,), (0o400,))
        if len(raw) != expected_size or hashlib.sha256(raw).hexdigest() != digest:
            raise ResearchBlobUnavailable("research_blob_hash_or_size_mismatch")
        return raw

    def _pending(self, digest: str, expected_size: int) -> None:
        name = ".pending-" + digest
        try:
            raw, pending = self._file(name, (1, 2), (0o400, 0o600))
        except FileNotFoundError:
            return
        if pending.st_nlink == 2:
            target_raw, target = self._file(digest, (2,), (0o400,))
            if (
                (pending.st_dev, pending.st_ino) != (target.st_dev, target.st_ino)
                or len(raw) != expected_size
                or target_raw != raw
                or hashlib.sha256(raw).hexdigest() != digest
            ):
                raise ResearchBlobUnavailable("ambiguous_research_pending")
        # Only this reserved non-artifact name is removed. Finalized blobs stay.
        os.unlink(name, dir_fd=self._fd)
        os.fsync(self._fd)

    def put(self, raw: bytes) -> ResearchBlobReceipt:
        if type(raw) is not bytes or len(raw) > MAX_SOURCE_BYTES:
            raise ResearchBlobUnavailable("research_blob_byte_limit")
        digest, size = hashlib.sha256(raw).hexdigest(), len(raw)
        with self._locked():
            self._pending(digest, size)
            try:
                self._read(digest, size)
            except FileNotFoundError:
                pending = ".pending-" + digest
                fd = os.open(
                    pending,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                    0o600,
                    dir_fd=self._fd,
                )
                with os.fdopen(fd, "wb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fchmod(stream.fileno(), 0o400)
                    os.fsync(stream.fileno())
                try:
                    os.link(pending, digest, src_dir_fd=self._fd, dst_dir_fd=self._fd, follow_symlinks=False)
                except FileExistsError:
                    # Never replace an existing target, including a corrupt one.
                    pass
                os.unlink(pending, dir_fd=self._fd)
                os.fsync(self._fd)
                self._read(digest, size)
        return ResearchBlobReceipt(digest, size)

    def read(self, digest: str, *, expected_size: int) -> bytes:
        if type(digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ResearchBlobUnavailable("invalid_research_blob_hash")
        if type(expected_size) is not int or not 0 <= expected_size <= MAX_SOURCE_BYTES:
            raise ResearchBlobUnavailable("research_blob_byte_limit")
        with self._locked():
            return self._read(digest, expected_size)
