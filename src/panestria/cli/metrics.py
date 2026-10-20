"""Owner-invoked performance snapshots; no backend, model or provider required."""

import json
from pathlib import Path
from typing import Annotated

import typer

from panestria.telemetry.performance import collect_performance, latest_snapshot, save_snapshot

metrics_app = typer.Typer(no_args_is_help=True)
DEFAULT = Path.home() / ".local/state/panestria/metrics"


@metrics_app.command("capture")
def capture(
    evidence_root: Annotated[Path, typer.Option()] = Path("evidence"),
    directory: Annotated[Path, typer.Option()] = DEFAULT,
    mutation_report: Annotated[list[Path] | None, typer.Option()] = None,
    ci_report: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Save named historical observations with original source/version and missing areas."""
    try:
        report = collect_performance(evidence_root, mutation_reports=tuple(mutation_report or []), ci_report=ci_report)
        path = save_snapshot(directory, report)
        typer.echo(json.dumps({"status": "SAVED", "path": str(path), "observations": len(report.observations)}))
    except Exception:
        typer.echo('{"status":"UNAVAILABLE","reason":"metrics_evidence_or_private_storage_invalid"}', err=True)
        raise typer.Exit(1) from None


@metrics_app.command("show")
def show(
    directory: Annotated[Path, typer.Option()] = DEFAULT,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show latest saved capture; separate cohorts, no overall accuracy percentage."""
    try:
        snapshot = latest_snapshot(directory)
        if as_json:
            typer.echo(snapshot.model_dump_json(indent=2))
            return
        typer.echo(f"Captured {snapshot.captured_at.isoformat()} | historical observations; no release authority")
        for item in snapshot.observations:
            value = "UNKNOWN" if item.value is None else f"{item.value:.4g} {item.unit}"
            source = item.source_commit[:7] if item.source_commit else "unknown"
            typer.echo(
                f"{item.metric}: {value} | {item.scope}/{item.fold or '-'} | "
                f"model={item.model or 'unknown'} | n={item.samples or 'unknown'} | source={source}"
            )
        typer.echo("NOT MEASURED: " + ", ".join(snapshot.missing_areas))
    except Exception:
        typer.echo('{"status":"UNAVAILABLE","reason":"metrics_history_unavailable_or_invalid"}', err=True)
        raise typer.Exit(1) from None
