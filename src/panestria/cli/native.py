"""Local metadata inspection and explicitly opted-in PUBLIC runtime qualification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from panestria.brokers.harness.cli_profile import BinaryPin, CliProfileProbe, NativeProbeUnavailable

native_app = typer.Typer(no_args_is_help=True)


@native_app.command("qualify-build")
def qualify_build_command(
    evidence_directory: Annotated[Path, typer.Option("--evidence-directory")],
    public_subscription_smoke: Annotated[bool, typer.Option("--public-subscription-smoke")] = False,
) -> None:
    """Run fixed PUBLIC conformance and issue an expiring runtime-only certificate."""
    from panestria.execution.native_qualification import QualificationUnavailable, qualify

    try:
        result = qualify(evidence_directory, public_subscription_smoke=public_subscription_smoke)
    except (QualificationUnavailable, OSError, ValueError):
        result = {"status": "UNAVAILABLE", "reason": "qualification_prerequisite_unavailable"}
    typer.echo(json.dumps(result, sort_keys=True))
    if result["status"] != "PASS":
        raise typer.Exit(1)


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
