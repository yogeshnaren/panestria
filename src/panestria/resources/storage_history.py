"""Explicit private bounded diagnostic history, never admission or cleanup authority."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
from dataclasses import replace
from datetime import UTC, datetime
from itertools import islice
from pathlib import Path
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from panestria.config_local import read_private
from panestria.contracts.storage_status import StorageCapacity
from panestria.resources import storage
from panestria.resources.storage import StorageReport, StorageSettings, StorageWarning

MAX_FILES = 512
MAX_BYTES = 4 * 1024 * 1024
MAX_SAMPLE = 16 * 1024
MAX_AGE_SECONDS = 86400


class _Snapshot(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)
    schema_version: Literal[1] = 1
    captured_at: AwareDatetime
    collector_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    settings_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    filesystem_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    report: StorageReport
    authority: Literal["DIAGNOSTIC_HISTORY_ONLY"] = "DIAGNOSTIC_HISTORY_ONLY"

    @model_validator(mode="after")
    def valid_baseline(self) -> Self:
        from dataclasses import asdict

        capacity = asdict(self.report.capacity)
        device = capacity.pop("device")
        StorageCapacity.model_validate_json(json.dumps(capacity, allow_nan=False))
        stamp = datetime.fromisoformat(self.report.observed_at)
        if (
            stamp.tzinfo is None
            or (device is not None and (type(device) is not int or device < 0))
            or self.report.cleanup_authority != "NONE"
            or self.report.permissions != "READ_ONLY_UNPRIVILEGED"
            or self.report.schema_version != 1
        ):
            raise ValueError("storage_history_baseline_unconfirmed")
        return self


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _filesystem_hash(path: Path) -> str:
    disk = os.statvfs(path)
    if type(disk.f_fsid) is not int:
        raise ValueError("filesystem_identity_unconfirmed")
    return _hash(f"{path.stat().st_dev}:{disk.f_fsid}:{disk.f_blocks}:{disk.f_frsize}".encode())


class StorageHistory:
    """One nonblocking writer; immutable samples stop at a fixed budget, never prune."""

    def __init__(self, settings: StorageSettings) -> None:
        self.settings = settings
        self.path = settings.history_directory if settings.notifications_enabled else None
        self.fd = -1
        self.directory_fd = -1
        self.directory: Path | None = None
        self.state = "DISABLED" if self.path is None else "UNAVAILABLE"
        self.samples: tuple[Path, ...] = ()
        self.settings_sha = _hash(settings.model_dump_json().encode())
        self.collector_sha = ""
        self.filesystem_sha = ""
        self.baseline_stamp: str | None = None

    def __enter__(self) -> Self:
        if self.path is None:
            return self
        try:
            if self.path.resolve() != self.path:
                raise ValueError
            self.path.mkdir(mode=0o700, parents=True, exist_ok=True)
            info = self.path.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError
            self.directory_fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            held = os.fstat(self.directory_fd)
            if (
                (held.st_dev, held.st_ino) != (info.st_dev, info.st_ino)
                or held.st_uid != os.getuid()
                or held.st_mode & 0o077
            ):
                raise ValueError
            self.directory = Path(f"/proc/self/fd/{self.directory_fd}")
            self.fd = os.open(self.directory / "capture.lock", os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            info = os.fstat(self.fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            entries = tuple(islice(self.directory.iterdir(), MAX_FILES + 1))
            if len(entries) > MAX_FILES or any(p.is_symlink() or not p.is_file() for p in entries):
                raise ValueError
            if sum(p.lstat().st_size for p in entries) > MAX_BYTES:
                raise ValueError
            self.samples = tuple(p for p in entries if p.name != "capture.lock")
            if any(len(p.stem) != 64 or p.suffix != ".json" for p in self.samples):
                raise ValueError
            self.collector_sha = _hash(
                (_hash(Path(storage.__file__).read_bytes()) + _hash(Path(__file__).read_bytes())).encode()
            )
            self.filesystem_sha = _filesystem_hash(self.settings.filesystem)
            self.state = "READY"
        except Exception:
            self.state = "UNAVAILABLE"
        return self

    def __exit__(self, *args: object) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1
        if self.directory_fd >= 0:
            os.close(self.directory_fd)
            self.directory_fd = -1

    def previous(self) -> StorageReport | None:
        if self.state != "READY":
            return None
        try:
            candidates = []
            for path in self.samples:
                raw = read_private(path, MAX_SAMPLE)
                if _hash(raw) != path.stem:
                    raise ValueError
                saved = _Snapshot.model_validate_json(raw)
                stamp = datetime.fromisoformat(saved.report.observed_at)
                if stamp.tzinfo is None or saved.report.cleanup_authority != "NONE":
                    raise ValueError
                age = (datetime.now(UTC) - stamp).total_seconds()
                if (
                    0 <= age <= MAX_AGE_SECONDS
                    and saved.collector_sha256 == self.collector_sha
                    and saved.settings_sha256 == self.settings_sha
                    and saved.filesystem_sha256 == self.filesystem_sha
                    and saved.report.filesystem == str(self.settings.filesystem)
                ):
                    candidates.append((stamp, saved.report))
            if not candidates:
                return None
            latest = max(candidates, key=lambda item: item[0])[1]
            self.baseline_stamp = latest.observed_at
            return latest
        except Exception:
            self.state = "UNAVAILABLE"
            return None

    def retain(self, report: StorageReport) -> StorageReport:
        if self.state == "DISABLED":
            return report
        try:
            if self.state != "READY" or self.path is None or self.directory is None:
                raise ValueError
            current, held = self.path.lstat(), os.fstat(self.directory_fd)
            if (
                not stat.S_ISDIR(current.st_mode)
                or (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino)
                or current.st_uid != os.getuid()
                or current.st_mode & 0o077
                or _filesystem_hash(self.settings.filesystem) != self.filesystem_sha
            ):
                raise ValueError
            if report.filesystem != str(self.settings.filesystem) or (
                report.capacity.device is not None and report.capacity.device != self.settings.filesystem.stat().st_dev
            ):
                raise ValueError
            sample = _Snapshot(
                captured_at=datetime.now(UTC),
                collector_sha256=self.collector_sha,
                settings_sha256=self.settings_sha,
                filesystem_sha256=self.filesystem_sha,
                report=report,
            )
            raw = sample.model_dump_json().encode()
            if len(raw) > MAX_SAMPLE:
                raise ValueError
            entries = tuple(islice(self.directory.iterdir(), MAX_FILES + 1))
            if len(entries) >= MAX_FILES or sum(p.lstat().st_size for p in entries) + len(raw) > MAX_BYTES:
                self.state = "FULL"
            else:
                fd = os.open(
                    self.directory / (_hash(raw) + ".json"),
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                )
                with os.fdopen(fd, "wb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                self.state = "SAVED"
        except Exception:
            self.state = "UNAVAILABLE"
        code = "storage_history_" + self.state.lower()
        notice = StorageWarning(
            code,
            "INFO" if self.state == "SAVED" else "WARNING",
            "Private diagnostic history: " + self.state + ". Fixed4MiB logical data/512-entry budget "
            "(filesystem overhead extra); no automatic deletion. "
            "Previous compatible retained sample: " + (self.baseline_stamp or "UNKNOWN") + ". "
            "Preserve history and choose another private directory or review capacity locally if full/unavailable. "
            "Past samples do not authorize writes, cleanup or release acceptance.",
        )
        return replace(report, warnings=(*report.warnings, notice))
