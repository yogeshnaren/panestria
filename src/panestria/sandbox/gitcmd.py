"""Allow only the Git commands the synthetic sandbox already uses."""

from __future__ import annotations

import re
from pathlib import Path

_SHA = re.compile(r"^[0-9a-f]{40}$")
_REF = re.compile(r"^(?:refs/)?[A-Za-z0-9_./-]{1,200}$")
_AUTHOR = "panestria-synthetic"
_EMAIL = "synthetic@panestria.invalid"
_HOOKS = "core.hooksPath=/dev/null"
_MESSAGES = frozenset({"synthetic-base", "synthetic-candidate"})


def allow_git(argv: list[str]) -> None:
    """Reject a Git invocation that is not one of the synthetic commands."""
    if not argv or argv[0] != "git":
        raise ValueError("git command")
    index = 1
    hooks_disabled = False
    while index < len(argv):
        token = argv[index]
        if token in {"-C", "--git-dir"}:
            if index + 1 >= len(argv):
                raise ValueError("git command")
            _filesystem(argv[index + 1])
            index += 2
            continue
        if token == "-c":
            if index + 1 >= len(argv) or argv[index + 1] != _HOOKS:
                raise ValueError("git command")
            hooks_disabled = True
            index += 2
            continue
        break
    if index >= len(argv):
        raise ValueError("git command")
    command = argv[index]
    args = argv[index + 1 :]
    if command == "init" and args[:2] == ["-b", "main"] and len(args) == 3:
        _filesystem(args[2])
        return
    if command == "config" and len(args) == 2:
        _config(args[0], args[1])
        return
    if command == "add" and len(args) == 1:
        _relative(args[0])
        return
    if command == "commit" and hooks_disabled and args[:1] == ["-m"] and len(args) == 2 and args[1] in _MESSAGES:
        return
    if command == "rev-parse" and _rev_parse(args):
        return
    if command == "worktree" and _worktree(args):
        return
    if command == "diff" and _diff(args):
        return
    if command == "ls-files" and args == ["--others", "--exclude-standard"]:
        return
    if command == "cat-file" and len(args) == 2 and args[0] == "-e" and _object_path(args[1]):
        return
    if command == "clone" and args[:1] == ["--bare"] and len(args) == 3:
        _filesystem(args[1])
        _filesystem(args[2])
        return
    if command == "branch" and args[:2] == ["-f", "synthetic-candidate"] and len(args) == 3 and _sha(args[2]):
        return
    if command == "fetch" and len(args) == 2 and args[1] == "synthetic-candidate:refs/panestria/candidate":
        _filesystem(args[0])
        return
    if command == "update-ref" and len(args) == 3 and _ref(args[0]) and _sha(args[1]) and _sha(args[2]):
        return
    raise ValueError("git command")


def _config(key: str, value: str) -> None:
    if key == "user.name" and value == _AUTHOR:
        return
    if key == "user.email" and value == _EMAIL:
        return
    if key == "core.hooksPath" and value == "/dev/null":
        return
    raise ValueError("git command")


def _rev_parse(args: list[str]) -> bool:
    if args == ["HEAD"]:
        return True
    if len(args) == 1 and _sha(args[0]):
        return True
    return len(args) == 2 and args[0] == "--verify" and _ref(args[1])


def _worktree(args: list[str]) -> bool:
    if args == ["prune"]:
        return True
    if len(args) == 4 and args[0] == "add" and args[1] == "--detach" and _sha(args[3]):
        _filesystem(args[2])
        return True
    return False


def _diff(args: list[str]) -> bool:
    if len(args) == 4 and args[:3] == ["--raw", "--find-renames", "--no-abbrev"] and _sha(args[3]):
        return True
    if len(args) == 5 and args[:4] == ["--cached", "--raw", "--find-renames", "--no-abbrev"] and _sha(args[4]):
        return True
    if len(args) == 5 and args[:2] == ["--raw", "--no-abbrev"] and args[3] == "--" and _sha(args[2]):
        _relative(args[4])
        return True
    return False


def _object_path(value: str) -> bool:
    base, separator, relative = value.partition(":")
    if separator != ":" or not _sha(base):
        return False
    _relative(relative)
    return True


def _sha(value: str) -> bool:
    return _SHA.fullmatch(value) is not None


def _ref(value: str) -> bool:
    return _REF.fullmatch(value) is not None and ".." not in Path(value).parts


def _relative(value: str) -> None:
    path = Path(value)
    if value == "" or value.startswith("-") or path.is_absolute() or ".." in path.parts:
        raise ValueError("git command")
    if "\n" in value or "\x00" in value:
        raise ValueError("git command")


def _filesystem(value: str) -> None:
    if value == "" or "\n" in value or "\x00" in value or ".." in Path(value).parts:
        raise ValueError("git command")
