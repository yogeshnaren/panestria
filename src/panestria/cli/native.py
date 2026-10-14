"""Explicit local metadata inspection; this command never starts an agent turn."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from panestria.brokers.harness.cli_profile import BinaryPin, CliProfileProbe, NativeProbeUnavailable

native_app = typer.Typer(no_args_is_help=True)


@native_app.command("inspect")
def inspect_command(
    binary: Annotated[Path, typer.Option("--binary")],
    expected_sha256: Annotated[str, typer.Option("--expected-sha256")],
    config_dir: Annotated[Path, typer.Option("--config-dir")],
    skills_archive: Annotated[Path, typer.Option("--skills-archive")],
) -> None:
    """Inspect a trusted pinned CLI and private native login directory."""
    try:
        manifest = CliProfileProbe(skills_archive).inspect(BinaryPin(binary, expected_sha256), config_dir)
    except NativeProbeUnavailable as exc:
        typer.echo(json.dumps({"code": str(exc), "retryable": False}), err=True)
        raise typer.Exit(2) from None
    typer.echo(manifest.model_dump_json())
    if manifest.status != "INSPECTED":
        raise typer.Exit(1)
