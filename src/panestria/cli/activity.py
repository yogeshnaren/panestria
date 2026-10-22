"""Explicit setup and foreground launch of the project metadata terminal."""

import fcntl
import json
import os
import stat
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer

from panestria.cli.tui import run_terminal
from panestria.cli.tui_client import ActivityClient
from panestria.config import ProfileRejected
from panestria.config_activity import ActivitySettings, load_activity_settings
from panestria.config_local import LocalApplicationRejected, create_local_token

activity_app = typer.Typer(no_args_is_help=True)


@activity_app.command("init")
def initialize(
    directory: Annotated[Path, typer.Option("--directory")],
    owner_id: Annotated[UUID, typer.Option("--owner-id")],
    project_id: Annotated[UUID, typer.Option("--project-id")],
    port: Annotated[int, typer.Option("--port", min=1, max=65535)] = 8769,
) -> None:
    """Prepare private files for existing IDs; do not create a project, grant or service."""
    try:
        if not directory.is_absolute() or directory.resolve() != directory:
            raise LocalApplicationRejected("local_init_path_or_port_invalid")
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
            path = directory / "activity.json"
            wanted = ActivitySettings(
                schema_version=1,
                owner_id=owner_id,
                project_id=project_id,
                bind_port=port,
                token_file=directory / "activity.token",
            )
            if not path.exists():
                if {p.name for p in directory.iterdir()} != {".init.lock"}:
                    raise LocalApplicationRejected("local_initialization_directory_not_empty")
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, "w") as stream:
                    stream.write(wanted.model_dump_json(indent=2) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                create_local_token(wanted.token_file)
                parent = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(parent)
                finally:
                    os.close(parent)
            actual, _ = load_activity_settings(path)
            if actual != wanted:
                raise LocalApplicationRejected("activity_configuration_conflict")
        finally:
            os.close(descriptor)
        typer.echo(
            json.dumps(
                {
                    "status": "CONFIGURED",
                    "config": str(path),
                    "server_started": False,
                    "project_created": False,
                    "authority": "READ_ONLY_METADATA",
                }
            )
        )
        return
    except LocalApplicationRejected as exc:
        code = exc.code
    except (OSError, ValueError):
        code = "activity_initialization_unavailable"
    typer.echo(json.dumps({"code": code, "files_preserved": True}), err=True)
    raise typer.Exit(2)


@activity_app.command("serve")
def serve(
    config: Annotated[Path, typer.Option("--config")],
    storage_config: Annotated[Path | None, typer.Option("--storage-config")] = None,
) -> None:
    """Run a loopback metadata server in this terminal; Ctrl+C stops it."""
    from panestria.api.activity_server import serve_activity

    try:
        if storage_config is None:
            serve_activity(config)
        else:
            serve_activity(config, storage_config=storage_config)
        return
    except (LocalApplicationRejected, ProfileRejected) as exc:
        code = exc.code
    except (OSError, ValueError):
        code = "activity_startup_failed"
    typer.echo(json.dumps({"code": code}), err=True)
    raise typer.Exit(2)


@activity_app.command("tui")
def terminal(config: Annotated[Path, typer.Option("--config")]) -> None:
    """Inspect existing project state without loading a model or starting work."""
    run_terminal(lambda: ActivityClient(config), metadata_only=True)
