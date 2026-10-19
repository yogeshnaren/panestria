"""Owner-invoked, local terminal storage report and opt-in warnings."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Annotated

import typer

from panestria.config_local import read_private
from panestria.resources.storage import StorageReport, StorageSettings, inspect_storage

storage_app = typer.Typer(no_args_is_help=True)


def _settings(path: Path | None) -> StorageSettings:
    return StorageSettings() if path is None else StorageSettings.model_validate_json(read_private(path, 16384))


@storage_app.command("inspect")
def inspect_command(
    config: Annotated[Path | None, typer.Option("--config")] = None,
    expected_write_bytes: Annotated[int, typer.Option(min=0)] = 0,
) -> None:
    """Show capacity and selected read-only estimates; never changes notification settings."""
    try:
        typer.echo(inspect_storage(_settings(config), expected_write_bytes=expected_write_bytes).to_json())
    except Exception:
        typer.echo('{"status":"UNAVAILABLE","reason":"storage_configuration_or_probe_failed"}', err=True)
        raise typer.Exit(1) from None


@storage_app.command("watch")
def watch_command(config: Annotated[Path, typer.Option("--config")]) -> None:
    """Foreground terminal warnings until Ctrl-C; enabled setting required, no daemon installation."""
    try:
        settings = _settings(config)
        if not settings.notifications_enabled:
            raise ValueError("storage_notifications_disabled")
    except Exception:
        typer.echo('{"status":"UNAVAILABLE","reason":"enable_storage_notifications_in_private_config"}', err=True)
        raise typer.Exit(1) from None
    previous: StorageReport | None = None
    signature: tuple[tuple[str, str], ...] | None = None
    try:
        while True:
            settings = _settings(config)
            if not settings.notifications_enabled:
                typer.echo('{"status":"STOPPED","reason":"storage_notifications_disabled"}')
                return
            report = inspect_storage(settings, previous=previous)
            current = tuple((item.code, item.severity) for item in report.warnings)
            if current != signature:
                typer.echo(report.to_json())  # Initial state, changed warnings, and recovery; no repeated spam.
                signature = current
            previous = report
            time.sleep(settings.interval_seconds)
    except KeyboardInterrupt:
        return
    except Exception:
        typer.echo('{"status":"UNAVAILABLE","reason":"storage_watch_stopped"}', err=True)
        raise typer.Exit(1) from None
