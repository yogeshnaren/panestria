"""Local owner research reviews, staging, explicit collection and evidence inspection."""

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
from panestria.config_research import load_research_settings
from panestria.contracts.research import ResearchLimits
from panestria.execution.research_brief import RetainedBrief, brief_html, brief_json
from panestria.execution.research_collection import OwnerCollection
from panestria.execution.research_policy import OwnerResearchPolicy
from panestria.execution.research_submission import stage_question
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor

research_app = typer.Typer(no_args_is_help=True)


@research_app.command("prepare-policy")
def prepare_research_policy(
    config: Annotated[Path, typer.Option("--config")],
    public_web_policy: Annotated[bool, typer.Option("--public-web-policy")] = False,
) -> None:
    """Show an exact pending PUBLIC-web grant for a dedicated research project; no I/O."""
    _research_policy(config, public_web_policy, None, None)


@research_app.command("confirm-policy")
def confirm_research_policy(
    review_id: str,
    effect_digest: str,
    config: Annotated[Path, typer.Option("--config")],
    public_web_policy: Annotated[bool, typer.Option("--public-web-policy")] = False,
) -> None:
    """Confirm the exact reviewed PUBLIC-web policy as local owner; no collection."""
    _research_policy(config, public_web_policy, review_id, effect_digest)


def _research_policy(config: Path, intent: bool, review: str | None, digest: str | None) -> None:
    try:
        if not intent:
            raise KernelDenied("explicit_public_web_policy_required")
        settings = load_research_settings(config)
        dsn = Settings(database_url=os.environ.get("PANESTRIA_DATABASE_URL", "")).validate_profile().database_url
        service = OwnerResearchPolicy(dsn.get_secret_value(), settings)
        if review is None:
            result = service.prepare(public_web_policy=intent)
        else:
            assert digest is not None
            result = service.confirm(review, digest, public_web_policy=intent)
    except KernelDenied as error:
        typer.echo(json.dumps({"status": "UNAVAILABLE", "reason": error.code}), err=True)
        raise typer.Exit(1) from None
    except Exception:
        typer.echo('{"status":"UNAVAILABLE","reason":"research_policy_not_confirmed"}', err=True)
        raise typer.Exit(1) from None
    typer.echo(json.dumps(result, sort_keys=True))


@research_app.command("collect")
def collect_research(
    request_id: str,
    config: Annotated[Path, typer.Option("--config")],
    queries: Annotated[Path, typer.Option("--queries")],
    output: Annotated[Path, typer.Option("--output")],
    public_web: Annotated[bool, typer.Option("--public-web")] = False,
    output_format: Annotated[Literal["html", "json"], typer.Option("--format")] = "html",
) -> None:
    """Explicit qualified PUBLIC collection; retained excerpts await synthesis/support."""
    try:
        if not public_web:
            raise ValueError("explicit_public_collection_required")
        # Catch ordinary export setup mistakes before any outward effect. The
        # final exclusive descriptor-based writer still enforces the boundary.
        if (
            not output.is_absolute()
            or output.parent.resolve(strict=True) != output.parent
            or stat.S_IMODE(output.parent.stat().st_mode) != 0o700
            or output.parent.stat().st_uid != os.getuid()
            or output.exists()
            or output.is_symlink()
        ):
            raise ValueError("new_private_output_required")
        settings = load_research_settings(config)
        raw_queries = json.loads(read_private(queries, 16 * 1024))
        if (
            type(raw_queries) is not list
            or not 1 <= len(raw_queries) <= 16
            or any(type(q) is not str for q in raw_queries)
        ):
            raise ValueError("bounded_public_queries_required")
        dsn = Settings(database_url=os.environ.get("PANESTRIA_DATABASE_URL", "")).validate_profile().database_url
        owner = OwnerCollection(dsn.get_secret_value(), settings)
        receipt = owner.collect(request_id, tuple(SecretStr(q) for q in raw_queries), public_web=public_web)
        brief = RetainedBrief(settings.root, owner.actor).inspect(dsn.get_secret_value(), request_id, receipt.task_id)
        raw = brief_html(brief) if output_format == "html" else brief_json(brief)
        _write_private(output, raw)
        typer.echo(
            json.dumps(
                {**asdict(receipt), "sha256": hashlib.sha256(raw).hexdigest(), "retained_excerpts": len(brief.claims)}
            )
        )
    except (Exception, KeyboardInterrupt):
        # Some work may already be committed. Never imply that retry is safe.
        typer.echo('{"status":"UNAVAILABLE","reason":"research_collection_unavailable_inspect_state"}', err=True)
        raise typer.Exit(1) from None


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
