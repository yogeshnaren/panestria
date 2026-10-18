"""Trusted process-local root handles; not a grant, account or execution broker.

No API/worker calls this primitive. Future broker callers must independently
authorize each effect before requesting a snapshot. Root references deliberately
do not survive restart, fork, reenrollment or descriptor loss.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import platform
import re
import secrets
import stat
import threading
import weakref
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Self
from uuid import UUID

from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor

MAX_ROOTS = 16
MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024
_NO_XDEV, _NO_MAGICLINKS, _NO_SYMLINKS, _BENEATH = 1, 2, 4, 8
_DESCENDANT = _NO_XDEV | _NO_MAGICLINKS | _NO_SYMLINKS | _BENEATH


class _OpenHow(ctypes.Structure):
    _fields_ = [("flags", ctypes.c_uint64), ("mode", ctypes.c_uint64), ("resolve", ctypes.c_uint64)]


def _open_path(parent: int, path: bytes, *, resolve: int, directory: bool = False) -> int:
    # Explicitly supported ABI only; no guessed syscall number or openat fallback.
    if platform.system() != "Linux" or platform.machine() != "x86_64" or ctypes.sizeof(ctypes.c_void_p) != 8:
        raise KernelDenied("connection_root_kernel_unsupported")
    flags = os.O_PATH | os.O_CLOEXEC | os.O_NOFOLLOW | (os.O_DIRECTORY if directory else 0)
    how = _OpenHow(flags, 0, resolve)
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        syscall = libc.syscall
    except (OSError, AttributeError):
        raise KernelDenied("connection_root_kernel_unsupported") from None
    syscall.restype = ctypes.c_long
    result = int(
        syscall(
            ctypes.c_long(437),
            ctypes.c_int(parent),
            ctypes.c_char_p(path),
            ctypes.byref(how),
            ctypes.c_size_t(ctypes.sizeof(how)),
        )
    )
    if result < 0:
        # Includes ENOSYS, unknown flags, EAGAIN, aliases and mount crossings.
        # No retry with weaker containment and no raw locator in diagnostics.
        raise KernelDenied("connection_root_unavailable")
    return result


def _scope(actor: Actor) -> tuple[str, str]:
    values = (actor.owner_id, actor.project_id)
    try:
        if any(type(value) is not str or len(value) != 36 or str(UUID(value)) != value for value in values):
            raise ValueError
    except (ValueError, AttributeError):
        raise KernelDenied("connection_root_unavailable") from None
    return values


def _path(value: str, *, absolute: bool) -> bytes:
    try:
        if type(value) is not str or not 1 <= len(value) <= 4095 or value.startswith("/") != absolute:
            raise ValueError
        encoded = value.encode("utf-8", errors="strict")
        if len(encoded) > 4095:
            raise ValueError
        pieces = (value[1:] if absolute else value).split("/")
        if (
            not 1 <= len(encoded) <= 4095
            or len(pieces) > 64
            or any(part in {"", ".", ".."} or len(part.encode("utf-8")) > 255 for part in pieces)
            or "\\" in value
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
        ):
            raise ValueError
        return encoded
    except (ValueError, UnicodeError):
        raise KernelDenied("connection_root_path_invalid") from None


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_uid,
        info.st_gid,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _directory(fd: int) -> os.stat_result:
    info = os.fstat(fd)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
        or info.st_nlink == 0
    ):
        raise KernelDenied("connection_root_unsafe")
    return info


def _regular(fd: int, root: os.stat_result, limit: int) -> os.stat_result:
    info = os.fstat(fd)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_dev != root.st_dev
        or info.st_nlink != 1
        or info.st_mode & 0o022
        or not 0 <= info.st_size <= limit
    ):
        raise KernelDenied("connection_root_unsafe")
    return info


def _chunks(fd: int, limit: int) -> Iterator[bytes]:
    size = 0
    while size <= limit:
        chunk = os.read(fd, min(65536, limit + 1 - size))
        if not chunk:
            return
        size += len(chunk)
        yield chunk


@dataclass(frozen=True)
class RootSnapshot:
    content: bytes = field(repr=False)
    sha256: str

    @property
    def size_bytes(self) -> int:
        return len(self.content)


def _close_roots(roots: dict[str, int]) -> None:
    for fd in roots.values():
        try:
            os.close(fd)
        except OSError:
            pass
    roots.clear()


class ConnectionRootSession:
    """Controller-only, explicit existing private directories; never persists paths.

    Enrollment pins the actual directory object, not its current pathname. A
    rename never retargets a handle. Fresh sessions issue fresh references and
    cannot restore an old declaration's root refs from dev/ino or path alone.
    """

    def __init__(self, actor: Actor) -> None:
        self._scope = _scope(actor)
        self._pid = os.getpid()
        self._mutex = threading.RLock()
        self._roots: dict[str, int] = {}
        self._cleanup = weakref.finalize(self, _close_roots, self._roots)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _process(self) -> None:
        if os.getpid() != self._pid:
            # Do not acquire a possibly inherited locked mutex after fork.
            self._cleanup()
            raise KernelDenied("connection_root_unavailable")

    @contextmanager
    def _locked(self, actor: Actor) -> Iterator[None]:
        self._process()
        if _scope(actor) != self._scope:
            raise KernelDenied("connection_root_unavailable")
        if not self._mutex.acquire(timeout=5):
            raise KernelDenied("connection_root_busy")
        try:
            if not self._cleanup.alive:
                raise KernelDenied("connection_root_unavailable")
            try:
                yield
            except OSError:
                raise KernelDenied("connection_root_unavailable") from None
        finally:
            self._mutex.release()

    def close(self) -> None:
        if os.getpid() != self._pid:
            self._cleanup()
            return
        with self._mutex:
            self._cleanup()

    def enroll(self, actor: Actor, absolute_locator: str) -> str:
        """Trusted setup only; no auto-discovery, mkdir, chmod or DB/event writes."""
        locator = _path(absolute_locator, absolute=True)
        with self._locked(actor):
            if len(self._roots) >= MAX_ROOTS:
                raise KernelDenied("connection_root_limit")
            # The explicit root may itself be on another mount. All path
            # components must be real directories, not symbolic/magic aliases.
            fd = _open_path(-100, locator, resolve=_NO_SYMLINKS | _NO_MAGICLINKS, directory=True)
            try:
                _directory(fd)
                reference = secrets.token_hex(32)
                if reference in self._roots:
                    raise KernelDenied("connection_root_unavailable")
                self._roots[reference] = fd
            except BaseException:
                os.close(fd)
                raise
            return reference

    def _root(self, reference: str) -> int:
        if type(reference) is not str or re.fullmatch(r"[0-9a-f]{64}", reference) is None:
            raise KernelDenied("connection_root_unavailable")
        fd = self._roots.get(reference)
        if fd is None:
            raise KernelDenied("connection_root_unavailable")
        return fd

    def remove(self, actor: Actor, reference: str) -> None:
        with self._locked(actor):
            fd = self._root(reference)
            del self._roots[reference]
            os.close(fd)

    def snapshot(self, actor: Actor, reference: str, relative_path: str, *, max_bytes: int) -> RootSnapshot:
        """Bounded bytes only. Caller must separately authorize read and purpose.

        This is neither a permission check nor hard interruptible I/O: regular
        files on a stalled filesystem can block despite O_NONBLOCK. It must not
        be exposed as a live connector before broker lifecycle integration.
        """
        relative = _path(relative_path, absolute=False)
        if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_SNAPSHOT_BYTES:
            raise KernelDenied("connection_root_byte_limit")
        with self._locked(actor):
            root_fd = self._root(reference)
            root = _directory(root_fd)
            path_fd = _open_path(root_fd, relative, resolve=_DESCENDANT)
            data_fd = check_fd = -1
            try:
                before = _regular(path_fd, root, max_bytes)
                # O_PATH first avoids opening a FIFO/socket/device for I/O.
                # Only this private, held, type-checked descriptor is reopened;
                # no caller-supplied /proc path or unvalidated second lookup.
                data_fd = os.open(f"/proc/self/fd/{path_fd}", os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK)
                if _identity(_regular(data_fd, root, max_bytes)) != _identity(before):
                    raise KernelDenied("connection_root_changed")
                raw = b"".join(_chunks(data_fd, max_bytes))
                digest = hashlib.sha256(raw).hexdigest()
                # Timestamp resolution alone cannot establish unchanged bytes.
                # Check a second bounded read of the same held regular object.
                # This is conservative observation, not an atomic FS snapshot.
                os.lseek(data_fd, 0, os.SEEK_SET)
                confirmed = hashlib.sha256()
                confirmed_size = 0
                for chunk in _chunks(data_fd, max_bytes):
                    confirmed.update(chunk)
                    confirmed_size += len(chunk)
                after = _regular(data_fd, root, max_bytes)
                check_fd = _open_path(root_fd, relative, resolve=_DESCENDANT)
                current = _regular(check_fd, root, max_bytes)
                _directory(root_fd)
                if (
                    len(raw) != before.st_size
                    or confirmed_size != len(raw)
                    or confirmed.hexdigest() != digest
                    or _identity(before) != _identity(after)
                    or _identity(before) != _identity(current)
                ):
                    raise KernelDenied("connection_root_changed")
                return RootSnapshot(raw, digest)
            finally:
                for descriptor in (check_fd, data_fd, path_fd):
                    if descriptor >= 0:
                        os.close(descriptor)
