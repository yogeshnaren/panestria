"""Separate exact local owner review and data packaging; never invoke a trainer."""

import json
import os
from pathlib import Path
from typing import Annotated, Any, Callable
from uuid import UUID

import typer
from pydantic import Field, StrictInt

from panestria.config import Settings
from panestria.contracts.curation import Closed
from panestria.kernel.goals import Actor
from panestria.learning.curation import ExampleCuration, _input

examples_app = typer.Typer(no_args_is_help=True)
Config = Annotated[Path, typer.Option("--config")]
Proofs = Annotated[list[Path] | None, typer.Option("--evidence")]


class CurationScope(Closed):
    schema_version: StrictInt = Field(ge=1, le=1)
    owner_id: UUID
    project_id: UUID


def _service(config: Path) -> ExampleCuration:
    scope = CurationScope.model_validate_json(_input(config, 4096))
    dsn = Settings(database_url=os.environ.get("PANESTRIA_DATABASE_URL", "")).validate_profile().database_url
    return ExampleCuration(Actor(str(scope.owner_id), str(scope.project_id)), dsn.get_secret_value())


def _finish(work: Callable[[], dict[str, Any]]) -> None:
    try:
        typer.echo(json.dumps(work(), ensure_ascii=True))
    except Exception:
        typer.echo('{"status":"UNAVAILABLE","reason":"curation_review_scope_evidence_or_storage_invalid"}', err=True)
        raise typer.Exit(1) from None


@examples_app.command("prepare")
def prepare(config: Config, candidate: Path, evidence: Proofs = None, days: int = 7) -> None:
    """Preview exact PUBLIC example, separate owner evidence and proposed eligibility; write nothing."""
    _finish(lambda: _service(config).prepare(candidate, tuple(evidence or []), days))


@examples_app.command("record")
def record(
    config: Config,
    candidate: Path,
    review_sha256: str,
    evidence: Proofs = None,
    days: int = 7,
    confirm_owner_review: bool = False,
    accept_training_data_purpose: bool = False,
) -> None:
    """Record exact owner judgments; ALLOWED additionally requires training-data-purpose consent."""
    _finish(
        lambda: _service(config).record(
            candidate,
            tuple(evidence or []),
            review_sha256,
            days=days,
            confirm_owner_review=confirm_owner_review,
            accept_training_data_purpose=accept_training_data_purpose,
        )
    )


@examples_app.command("export")
def export(config: Config, review: Annotated[list[str], typer.Option("--review")], output: Path) -> None:
    """Package up to16 currently allowed originals locally; refuse stale/withdrawn/conflicting records."""
    _finish(lambda: _service(config).export(tuple(review), output))


@examples_app.command("validate-export")
def validate_export(config: Config, packet: Path) -> None:
    """Recheck copied/restored packet against current canonical decisions; file possession grants no rights."""
    _finish(lambda: _service(config).validate_export(packet))


@examples_app.command("withdraw")
def withdraw(config: Config, review_sha256: str, confirm_withdrawal: bool = False) -> None:
    """Permanently withdraw the same content in this project, preserving history and existing files."""
    _finish(lambda: _service(config).withdraw(review_sha256, confirm=confirm_withdrawal))
