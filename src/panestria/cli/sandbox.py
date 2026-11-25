"""Owner-invoked sandbox setup commands."""

from __future__ import annotations

import json

import typer

from panestria.sandbox.images import ImageUnavailable, prepare_worker_image
from panestria.sandbox.profiles import DEFAULT_IMAGE

sandbox_app = typer.Typer(no_args_is_help=True)


@sandbox_app.command("prepare-image")
def prepare_image_command() -> None:
    """Pull the pinned worker image by digest if it is missing. Workers never pull."""
    try:
        status = prepare_worker_image()
    except ImageUnavailable as exc:
        typer.echo(json.dumps({"code": exc.code, "image": DEFAULT_IMAGE}), err=True)
        raise typer.Exit(1) from None
    typer.echo(json.dumps({"status": status, "image": DEFAULT_IMAGE}))
