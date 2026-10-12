"""Reviewed command refs. Worker-supplied tests are not part of the required set."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RegisteredCommand:
    ref: str
    argv: tuple[str, ...]
    required: bool
    script_sha256: str


class CommandRegistry:
    def __init__(self, bundle_root: Path, interpreter: str, commands: tuple[RegisteredCommand, ...]) -> None:
        self.bundle_root = bundle_root.resolve()
        self.interpreter = interpreter
        self._commands = {command.ref: command for command in commands}

    @classmethod
    def load(cls, bundle_root: Path, interpreter: str) -> CommandRegistry:
        script = bundle_root / "required_check.py"
        digest = hashlib.sha256(script.read_bytes()).hexdigest()
        command = RegisteredCommand(
            "synthetic-required",
            (interpreter, str(script.resolve())),
            True,
            digest,
        )
        return cls(bundle_root, interpreter, (command,))

    def required(self) -> tuple[RegisteredCommand, ...]:
        return tuple(command for command in self._commands.values() if command.required)

    def resolve(self, ref: str) -> RegisteredCommand:
        try:
            return self._commands[ref]
        except KeyError:
            raise KeyError(ref) from None

    def add_worker_command(self, ref: str, argv: tuple[str, ...]) -> None:
        raise PermissionError(f"worker cannot register {ref}")
