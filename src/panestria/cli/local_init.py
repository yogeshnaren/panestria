"""Private first-run files, stable identities and explicit offline-only setup."""

import fcntl
import json
import os
import shlex
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from panestria.config_local import (
    LocalApplicationRejected,
    LocalApplicationSettings,
    create_local_token,
    load_local_settings,
)


@contextmanager
def first_run_files(directory: Path, model_cache: Path, port: int) -> Iterator[LocalApplicationSettings]:
    """Hold one initialization lock through DB commit; never replace existing files."""
    if (
        not directory.is_absolute()
        or directory.resolve() != directory
        or not model_cache.is_absolute()
        or model_cache.is_symlink()
        or not 1 <= port <= 65535
    ):
        raise LocalApplicationRejected("local_init_path_or_port_invalid")
    if not model_cache.is_dir() or {p.name for p in model_cache.iterdir()} != {"blobs", "manifests"}:
        raise LocalApplicationRejected("dedicated_model_cache_required")
    if directory.is_relative_to(model_cache.resolve()) or model_cache.resolve().is_relative_to(directory):
        raise LocalApplicationRejected("local_path_overlap")
    directory.mkdir(mode=0o700, exist_ok=True)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise LocalApplicationRejected("local_directory_must_be_private")
    descriptor = os.open(directory / ".init.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise LocalApplicationRejected("local_file_must_be_private")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LocalApplicationRejected("local_initialization_busy") from None
        path = directory / "local.json"
        if not path.exists():
            if {p.name for p in directory.iterdir()} != {".init.lock"}:
                raise LocalApplicationRejected("local_initialization_directory_not_empty")
            config = LocalApplicationSettings(
                schema_version=1,
                owner_id=uuid4(),
                project_id=uuid4(),
                bind_port=port,
                token_file=directory / "local.token",
                model_cache=model_cache,
                runtime_directory=directory / "runtime",
            )
            # Record identities before any token or DB effect. Partial files are
            # preserved on error and never replaced by another random identity.
            config_fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(config_fd, "w") as stream:
                stream.write(config.model_dump_json(indent=2) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            create_local_token(config.token_file)
            parent_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        config, _ = load_local_settings(path)
        if (
            config.model_cache != model_cache
            or config.bind_port != port
            or config.bind_host != "127.0.0.1"
            or config.token_file != directory / "local.token"
            or config.runtime_directory != directory / "runtime"
        ):
            raise LocalApplicationRejected("local_initialization_configuration_conflict")
        yield config
    finally:
        os.close(descriptor)


def configured_message(directory: Path, receipt: dict[str, object]) -> str:
    config = shlex.quote(str(directory / "local.json"))
    return json.dumps(
        {
            "schema_version": 1,
            "status": "CONFIGURED",
            **receipt,
            "server_started": False,
            "next_steps": [
                "panestria local serve --config " + config,
                "panestria tui --config " + config,
            ],
        }
    )
