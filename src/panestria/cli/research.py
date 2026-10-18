"""Local owner question staging and evidence inspection; no search/fetch/model execution."""

import hashlib
import json
import os
import stat
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Literal

import typer
from pydantic import SecretStr

from panestria.config import Settings
from panestria.config_local import read_private
from panestria.contracts.research import ResearchLimits
from panestria.execution.research_brief import RetainedBrief, brief_html, brief_json
from panestria.execution.research_submission import stage_question
from panestria.kernel.goals import Actor

research_app = typer.Typer(no_args_is_help=True)


@research_app.command("stage")
def stage_research(
    owner_id: str,
    project_id: str,
    contract: Annotated[Path, typer.Option("--contract")],
    question: Annotated[Path, typer.Option("--question")],
    limits: Annotated[Path, typer.Option("--limits")],
    store: Annotated[Path, typer.Option("--store")],
    key: Annotated[str, typer.Option("--key")],
    public_question: Annotated[bool, typer.Option("--public-question")] = False,
) -> None:
    """Stage one explicit PUBLIC question locally. Does not search, fetch, activate or complete a task."""
    try:
        if not public_question:
            raise ValueError("explicit_public_question_required")
        dsn = Settings(database_url=os.environ.get("PANESTRIA_DATABASE_URL", "")).validate_profile().database_url
        receipt = stage_question(
            dsn.get_secret_value(),
            Actor(owner_id, project_id),
            store,
            json.loads(read_private(contract, 256 * 1024)),
            SecretStr(read_private(question, 65536).decode("utf-8")),
            ResearchLimits.model_validate_json(read_private(limits, 8192)),
            key,
            public_question=public_question,
        )
        typer.echo(json.dumps(asdict(receipt)))
    except Exception:
        typer.echo('{"status":"UNAVAILABLE","reason":"research_question_not_staged"}', err=True)
        raise typer.Exit(1) from None


def _write_private(path: Path, raw: bytes) -> None:
    if not path.is_absolute() or path.parent.resolve(strict=True) != path.parent:
        raise ValueError("noncanonical_output")
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(parent)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError("private_output_directory_required")
        fd = os.open(
            path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=parent
        )
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(parent)
    finally:
        os.close(parent)


@research_app.command("inspect")
def inspect_research(
    owner_id: str,
    project_id: str,
    request_id: str,
    task_id: str,
    store: Annotated[Path, typer.Option("--store")],
    output: Annotated[Path, typer.Option("--output")],
    output_format: Annotated[Literal["html", "json"], typer.Option("--format")] = "html",
) -> None:
    """Recheck retained evidence; export to a new private file. Administrative local DB access required."""
    try:
        dsn = Settings(database_url=os.environ.get("PANESTRIA_DATABASE_URL", "")).validate_profile().database_url
        brief = RetainedBrief(store, Actor(owner_id, project_id)).inspect(dsn.get_secret_value(), request_id, task_id)
        raw = brief_html(brief) if output_format == "html" else brief_json(brief)
        _write_private(output, raw)
        typer.echo(
            json.dumps(
                {
                    "status": "EXPORTED",
                    "purpose": brief.purpose,
                    "privacy_label": brief.privacy_label,
                    "claim_count": len(brief.claims),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "semantic_support": "NOT_ASSESSED",
                    "task_completion_authority": "NONE",
                }
            )
        )
    except Exception:
        # No DSN, question, claim, URL, path or raw exception in terminal output.
        typer.echo('{"status":"UNAVAILABLE","reason":"research_inspection_not_exported"}', err=True)
        raise typer.Exit(1) from None
