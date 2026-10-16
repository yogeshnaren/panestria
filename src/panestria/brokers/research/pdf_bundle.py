"""Pin a minimal dependency bundle for a later isolated PDF reader, never parse PDFs here."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from importlib.metadata import distribution
from pathlib import Path, PurePosixPath

PYPDF_VERSION = "6.20.1"
PYPDF_BUNDLE_SHA256 = "ee7677af7c459d97f4d1ee9a715e5b4d19fecb3295d2d596b6d4a6ac076b6c5a"


class PdfBundleUnavailable(ValueError):
    pass


@dataclass(frozen=True)
class PdfBundle:
    directory: Path
    manifest_sha256: str
    file_count: int
    size_bytes: int


def _safe_file(path: Path, *, installed_source: bool = False) -> bytes:
    if path.resolve(strict=True) != path:
        raise ValueError
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_mode & (0o002 if installed_source else 0o022)
            or info.st_uid not in {0, os.getuid()}
        ):
            raise ValueError
        raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError
        return raw


def _manifest(files: dict[str, bytes]) -> bytes:
    return json.dumps(
        {
            "version": PYPDF_VERSION,
            "files": [
                {"path": name, "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
                for name, raw in sorted(files.items())
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _installed_files() -> dict[str, bytes]:
    package = distribution("pypdf")
    if package.version != PYPDF_VERSION or package.files is None:
        raise ValueError
    files: dict[str, bytes] = {}
    for entry in package.files:
        source = str(entry)
        if source.startswith("pypdf/") and "__pycache__" not in PurePosixPath(source).parts:
            name = source
        elif source == "pypdf-" + PYPDF_VERSION + ".dist-info/licenses/LICENSE":
            name = "LICENSE-pypdf"
        else:
            continue
        if (
            PurePosixPath(name).is_absolute()
            or any(part in {".", ".."} for part in PurePosixPath(name).parts)
            or name in files
        ):
            raise ValueError
        files[name] = _safe_file(Path(str(package.locate_file(entry))), installed_source=True)
        if len(files) > 128 or sum(map(len, files.values())) > 8 * 1024 * 1024:
            raise ValueError
    if len(files) != 61 or hashlib.sha256(_manifest(files)).hexdigest() != PYPDF_BUNDLE_SHA256:
        raise ValueError
    return files


def _private(path: Path) -> None:
    info = path.lstat()
    if (
        path.resolve(strict=True) != path
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise ValueError


def stage_pdf_bundle(directory: Path) -> PdfBundle:
    """New owned private destination only. A partial failed stage is never a usable bundle."""
    try:
        _private(directory.parent)
        if not directory.is_absolute() or directory.exists() or directory.is_symlink():
            raise ValueError
        files = _installed_files()  # Verify complete immutable manifest before creating any output.
        directory.mkdir(mode=0o700)
        for name, raw in {**files, "manifest.json": _manifest(files)}.items():
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o400)
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        receipt = PdfBundle(directory, PYPDF_BUNDLE_SHA256, len(files), sum(map(len, files.values())))
        verify_pdf_bundle(receipt)
        return receipt
    except Exception:
        raise PdfBundleUnavailable("pdf_bundle_unavailable") from None


def verify_pdf_bundle(bundle: PdfBundle) -> None:
    try:
        _private(bundle.directory)
        files: dict[str, bytes] = {}
        for path in bundle.directory.rglob("*"):
            info = path.lstat()
            if stat.S_ISDIR(info.st_mode):
                _private(path)
                continue
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o400:
                raise ValueError
            name = path.relative_to(bundle.directory).as_posix()
            raw = _safe_file(path)
            if name == "manifest.json":
                if hashlib.sha256(raw).hexdigest() != PYPDF_BUNDLE_SHA256:
                    raise ValueError
            else:
                files[name] = raw
            if len(files) > 128 or sum(map(len, files.values())) > 8 * 1024 * 1024:
                raise ValueError
        manifest = _manifest(files)
        if (
            bundle.manifest_sha256 != PYPDF_BUNDLE_SHA256
            or len(files) != bundle.file_count
            or len(files) != 61
            or sum(map(len, files.values())) != bundle.size_bytes
            or hashlib.sha256(manifest).hexdigest() != PYPDF_BUNDLE_SHA256
            or _safe_file(bundle.directory / "manifest.json") != manifest
        ):
            raise ValueError
    except Exception:
        raise PdfBundleUnavailable("pdf_bundle_integrity_unconfirmed") from None
