"""Materialize an exact protected Git tree without checkout hooks, filters or .git."""

from __future__ import annotations

import hashlib
import json
import os
import re
import selectors
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from functools import partial
from pathlib import Path, PurePosixPath

from panestria.contracts.private_paths import folded_name


class SnapshotRejected(Exception):
    pass


@dataclass(frozen=True)
class GitSnapshot:
    directory: Path
    tree: str
    manifest_sha256: str
    changed_paths: tuple[str, ...]
    files: tuple[tuple[str, str, int, str], ...]


def protected_git(
    repository: Path,
    args: tuple[str, ...],
    *,
    limit: int = 4 * 1024 * 1024,
    input_data: bytes | None = None,
    deadline: float | None = None,
) -> bytes:
    if input_data is not None and (type(input_data) is not bytes or len(input_data) > 8 * 1024 * 1024):
        raise SnapshotRejected("git_input_limit")
    deadline = min(time.monotonic() + 10, deadline) if deadline is not None else time.monotonic() + 10
    if deadline <= time.monotonic():
        raise SnapshotRejected("git_timeout")
    env = {
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "HOME": str(repository.parent),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_ALLOW_PROTOCOL": "file",
    }
    # A private seekable input avoids pipe deadlocks and never exposes candidate
    # bytes as argv, shell syntax, filters or repository-owned commands.
    with tempfile.TemporaryFile() as source:
        if input_data is not None:
            source.write(input_data)
            source.seek(0)
        process = subprocess.Popen(
            (
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "core.fsmonitor=false",
                "--git-dir",
                str(repository),
                *args,
            ),
            env=env,
            stdin=source if input_data is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    assert process.stdout is not None and process.stderr is not None
    output = bytearray()
    total = 0
    with selectors.DefaultSelector() as selector:
        for stream in (process.stdout, process.stderr):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, stream is process.stdout)
        try:
            while selector.get_map():
                if time.monotonic() >= deadline:
                    raise SnapshotRejected("git_timeout")
                for key, _ in selector.select(min(0.05, deadline - time.monotonic())):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    total += len(chunk)
                    if total > limit:
                        raise SnapshotRejected("git_output_limit")
                    if key.data:
                        output.extend(chunk)
            process.wait(timeout=max(0.001, deadline - time.monotonic()))
            if process.returncode:
                raise SnapshotRejected("protected_git_failed")
            return bytes(output)
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=2)
            process.stdout.close()
            process.stderr.close()


def _safe_path(raw: bytes) -> str:
    try:
        name = raw.decode("utf-8")
    except UnicodeError:
        raise SnapshotRejected("unsupported_path_encoding") from None
    path = PurePosixPath(name)
    folded = [folded_name(part) for part in path.parts]
    if (
        not name
        or path.is_absolute()
        or path.as_posix() != name
        or any(part in {".", ".."} for part in path.parts)
        or any(part in {".git", ".ssh", ".aws", ".claude", "secrets"} or part.startswith(".env") for part in folded)
        or any(ord(character) < 32 for character in name)
        or "\\" in name
        or (folded and folded[-1] == ".mcp.json")
    ):
        raise SnapshotRejected("unsafe_candidate_path")
    return name


def materialize(
    repository: Path, base: str, candidate: str, directory: Path, *, deadline: float | None = None
) -> GitSnapshot:
    git = partial(protected_git, repository, deadline=deadline)
    if not all(re.fullmatch(r"[0-9a-f]{40}", value) for value in (base, candidate)):
        raise SnapshotRejected("invalid_git_identity")
    if repository.is_symlink() or not repository.is_dir() or directory.exists() or directory.is_symlink():
        raise SnapshotRejected("invalid_snapshot_scope")
    if git(("rev-parse", "--is-bare-repository")).strip() != b"true":
        raise SnapshotRejected("candidate_repository_not_bare")
    git(("merge-base", "--is-ancestor", base, candidate))
    tree = git(("rev-parse", "--verify", candidate + "^{tree}")).decode().strip()
    if not re.fullmatch(r"[0-9a-f]{40}", tree):
        raise SnapshotRejected("invalid_git_tree")
    changed = tuple(
        sorted(
            _safe_path(name)
            for name in git(
                ("diff", "--no-ext-diff", "--no-textconv", "--no-renames", "--name-only", "-z", base, candidate),
            ).split(b"\0")
            if name
        )
    )
    records: list[tuple[str, str, int, str]] = []
    size = 0
    listing = git(("ls-tree", "-r", "-l", "-z", candidate))
    for entry in listing.split(b"\0"):
        if not entry:
            continue
        header, raw_name = entry.split(b"\t", 1)
        mode, kind, oid, raw_size = header.split()
        name = _safe_path(raw_name)
        if mode not in {b"100644", b"100755"} or kind != b"blob" or not re.fullmatch(rb"[0-9a-f]{40}", oid):
            raise SnapshotRejected("unsupported_git_entry")
        count = int(raw_size)
        size += count
        if count > 8 * 1024 * 1024 or size > 32 * 1024 * 1024 or len(records) >= 2000:
            raise SnapshotRejected("snapshot_size_limit")
        records.append((name, oid.decode(), count, mode.decode()))
    directory.mkdir(parents=True, mode=0o700)
    manifest = []
    files: list[tuple[str, str, int, str]] = []
    for name, object_id, count, file_mode in sorted(records):
        content = git(("cat-file", "blob", object_id), limit=count + 1024)
        if len(content) != count:
            raise SnapshotRejected("blob_size_mismatch")
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_bytes(content)
        path.chmod(0o444)
        content_sha = hashlib.sha256(content).hexdigest()
        manifest.append({"path": name, "sha256": content_sha, "size": count, "git_mode": file_mode})
        files.append((name, content_sha, count, file_mode))
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return GitSnapshot(directory, tree, digest, changed, tuple(files))


def verify_snapshot(snapshot: GitSnapshot) -> None:
    import stat

    if snapshot.directory.is_symlink():
        raise SnapshotRejected("snapshot_changed")
    observed = []
    for path in snapshot.directory.rglob("*"):
        if path.is_symlink():
            raise SnapshotRejected("snapshot_changed")
        if path.is_dir():
            continue
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise SnapshotRejected("snapshot_changed")
        observed.append(path.relative_to(snapshot.directory).as_posix())
    if sorted(observed) != [entry[0] for entry in snapshot.files]:
        raise SnapshotRejected("snapshot_changed")
    manifest = []
    for name, digest, size, mode in snapshot.files:
        path = snapshot.directory / name
        with path.open("rb") as stream:
            raw = stream.read(size + 1)
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
            raise SnapshotRejected("snapshot_changed")
        manifest.append({"path": name, "sha256": digest, "size": size, "git_mode": mode})
    actual = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if actual != snapshot.manifest_sha256:
        raise SnapshotRejected("snapshot_changed")
