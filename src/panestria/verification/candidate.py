"""Freeze stopped worker bytes into protected Git objects without using its Git.

No ref is changed here. Independent verification and exact protected-ref
approval are separate. Call only after the worker container has been reaped.
"""

from __future__ import annotations

import os
import re
import stat
from functools import partial
from pathlib import Path

from panestria.verification.git_snapshot import SnapshotRejected, _safe_path, protected_git


def _walk_error(_error: OSError) -> None:
    raise SnapshotRejected("candidate_capture_unavailable")


def capture_candidate(repository: Path, base: str, workspace: Path, *, deadline: float | None = None) -> str:
    git = partial(protected_git, repository, deadline=deadline)
    if (
        not re.fullmatch(r"[0-9a-f]{40}", base)
        or repository.is_symlink()
        or not repository.is_dir()
        or workspace.is_symlink()
        or not workspace.is_absolute()
        or workspace.resolve() != workspace
        or not workspace.is_dir()
        or workspace.is_relative_to(repository)
        or repository.is_relative_to(workspace)
    ):
        raise SnapshotRejected("invalid_candidate_scope")
    if git(("rev-parse", "--is-bare-repository")).strip() != b"true":
        raise SnapshotRejected("candidate_repository_not_bare")
    git(("cat-file", "-e", base + "^{commit}"))
    # Snapshot bytes first. The object importer never runs in the workspace,
    # never reads .git/config or .gitattributes, and never runs worker tests.
    files: list[tuple[str, bytes, str]] = []
    total = entries = 0
    try:
        for parent, directories, names, directory_fd in os.fwalk(workspace, follow_symlinks=False, onerror=_walk_error):
            entries += len(directories) + len(names)
            if entries > 4000:
                raise SnapshotRejected("candidate_entry_limit")
            relative = Path(parent).relative_to(workspace)
            for name in directories:
                _safe_path((relative / name).as_posix().encode())
                if not stat.S_ISDIR(os.stat(name, dir_fd=directory_fd, follow_symlinks=False).st_mode):
                    raise SnapshotRejected("unsupported_candidate_entry")
            for name in names:
                path = _safe_path((relative / name).as_posix().encode())
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
                try:
                    info = os.fstat(fd)
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                        raise SnapshotRejected("unsupported_candidate_entry")
                    total += info.st_size
                    if info.st_size > 8 * 1024 * 1024 or total > 32 * 1024 * 1024 or len(files) >= 2000:
                        raise SnapshotRejected("candidate_size_limit")
                    with os.fdopen(fd, "rb", closefd=False) as stream:
                        raw = stream.read(info.st_size + 1)
                    current = os.fstat(fd)
                    fields = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
                    if len(raw) != info.st_size or any(
                        getattr(current, field) != getattr(info, field) for field in fields
                    ):
                        raise SnapshotRejected("candidate_changed_during_capture")
                    files.append((path, raw, "100755" if info.st_mode & 0o111 else "100644"))
                finally:
                    os.close(fd)
    except (OSError, UnicodeError):
        raise SnapshotRejected("candidate_capture_unavailable") from None
    trees: dict[str, list[tuple[str, str, str, str]]] = {"": []}
    for path, raw, mode in sorted(files):
        file_path = Path(path)
        parent = "" if file_path.parent.as_posix() == "." else file_path.parent.as_posix()
        oid = git(("hash-object", "-w", "--no-filters", "--stdin"), input_data=raw).decode().strip()
        if not re.fullmatch(r"[0-9a-f]{40}", oid):
            raise SnapshotRejected("invalid_candidate_object")
        trees.setdefault(parent, []).append((mode, "blob", oid, file_path.name))
        while parent:
            trees.setdefault(parent, [])
            parent = "" if Path(parent).parent.as_posix() == "." else Path(parent).parent.as_posix()
    # Deepest directories first, then their parent entries. Git mktree validates
    # object kinds/modes; no index, checkout, hooks, filters or host shell exists.
    tree = ""
    for directory in sorted(trees, key=lambda value: (-len(Path(value).parts), value)):
        listing = b"".join(
            f"{mode} {kind} {oid}\t{name}".encode() + b"\0" for mode, kind, oid, name in trees[directory]
        )
        tree = git(("mktree", "-z"), input_data=listing).decode().strip()
        if not re.fullmatch(r"[0-9a-f]{40}", tree):
            raise SnapshotRejected("invalid_candidate_tree")
        if directory:
            directory_path = Path(directory)
            parent = "" if directory_path.parent.as_posix() == "." else directory_path.parent.as_posix()
            trees.setdefault(parent, []).append(("040000", "tree", tree, directory_path.name))
    candidate = (
        git(
            (
                "-c",
                "user.name=Panestria worker candidate",
                "-c",
                "user.email=worker@panestria.invalid",
                "commit-tree",
                tree,
                "-p",
                base,
                "-m",
                "Build candidate awaiting independent verification",
            ),
        )
        .decode()
        .strip()
    )
    if not re.fullmatch(r"[0-9a-f]{40}", candidate):
        raise SnapshotRejected("invalid_candidate_commit")
    return candidate
