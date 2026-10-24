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


@research_app.command("guide")
def guided_research(
    request_id: str,
    synthesis_config: Annotated[Path, typer.Option("--synthesis-config", "--config")],
    collection_config: Annotated[Path | None, typer.Option("--collection-config")] = None,
) -> None:
    """Review each existing stage of the SAME staged PUBLIC request in a terminal."""
    from panestria.cli.research_guide_terminal import run_research_guide_terminal
    from panestria.config_synthesis import load_synthesis_settings
    from panestria.execution.research_guide import OwnerResearchGuide

    try:
        settings = load_synthesis_settings(synthesis_config, need_model=False)
        collection = load_research_settings(collection_config) if collection_config is not None else None
        dsn = Settings(database_url=os.environ.get("PANESTRIA_DATABASE_URL", "")).validate_profile().database_url
        run_research_guide_terminal(OwnerResearchGuide(dsn.get_secret_value(), settings, collection), request_id)
    except (Exception, KeyboardInterrupt):
        typer.echo('{"status":"UNAVAILABLE","reason":"research_guide_unavailable_inspect_state"}', err=True)
        raise typer.Exit(1) from None


@research_app.command("plan-queries")
def plan_queries(
    request_id: str,
    config: Annotated[Path, typer.Option("--config")],
    output: Annotated[Path, typer.Option("--output")],
    key: Annotated[str, typer.Option("--key")],
    retain_local_plan: bool = False,
) -> None:
    """Retain a bounded local proposal and export plain queries for separate PUBLIC collection."""
    _query_plan_export(request_id, config, output, key, retain_local_plan)


@research_app.command("query-plan")
def query_plan(
    request_id: str,
    config: Annotated[Path, typer.Option("--config")],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    """Export retained query data and show measurements without loading a model."""
    _query_plan_export(request_id, config, output, None, False)


def _query_plan_export(request_id: str, config: Path, output: Path, key: str | None, intent: bool) -> None:
    from panestria.config_synthesis import load_synthesis_settings
    from panestria.execution.research_query_plan import OwnerQueryPlan

    try:
        if key is not None and not intent:
            raise KernelDenied("explicit_retained_local_query_plan_required")
        if (
            not output.is_absolute()
            or output.parent.resolve(strict=True) != output.parent
            or stat.S_IMODE(output.parent.stat().st_mode) != 0o700
            or output.parent.stat().st_uid != os.getuid()
            or output.exists()
            or output.is_symlink()
        ):
            raise KernelDenied("new_private_query_export_required")
        settings = load_synthesis_settings(config, need_model=key is not None)
        dsn = Settings(database_url=os.environ.get("PANESTRIA_DATABASE_URL", "")).validate_profile().database_url
        service = OwnerQueryPlan(dsn.get_secret_value(), settings)
        receipt = service.plan(request_id, key, retain_local_plan=True) if key is not None else {}
        if key is not None and receipt["status"] != "QUERY_PLAN_RETAINED":
            raise KernelDenied("query_plan_unconfirmed_inspect_canonical_state")
        retained = service.inspect(request_id)
        if key is None:
            receipt = {
                "status": "QUERY_PLAN_EXPORTED",
                "plan_id": retained.plan_id,
                "web_authority": "NONE",
                "task_completion_authority": "NONE",
            }
        _write_private(
            output, json.dumps([q.get_secret_value() for q in retained.response.queries], ensure_ascii=False).encode()
        )
    except KernelDenied as exc:
        typer.echo(json.dumps({"status": "UNAVAILABLE", "reason": exc.code}), err=True)
        raise typer.Exit(1) from None
    except Exception:
        typer.echo('{"status":"UNAVAILABLE","reason":"query_plan_not_confirmed_inspect_state"}', err=True)
        raise typer.Exit(1) from None
    typer.echo(
        json.dumps(
            {
                **receipt,
                "query_count": len(retained.response.queries),
                "question_shortened": retained.packet.question_shortened,
                "model_ref": retained.model_ref,
                "model_digest": retained.model_digest,
                "input_tokens": retained.input_tokens,
                "output_tokens": retained.output_tokens,
                "model_request_elapsed_seconds": retained.model_request_elapsed_seconds,
                "query_quality": retained.query_quality,
            },
            sort_keys=True,
        )
    )


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


def _draft_output_preflight(output: Path) -> None:
    if (
        not output.is_absolute()
        or output.parent.resolve(strict=True) != output.parent
        or stat.S_IMODE(output.parent.stat().st_mode) != 0o700
        or output.parent.stat().st_uid != os.getuid()
        or output.exists()
        or output.is_symlink()
    ):
        raise ValueError("new_private_output_required")


@research_app.command("synthesize")
def synthesize_research(
    request_id: str,
    config: Annotated[Path, typer.Option("--config")],
    key: Annotated[str, typer.Option("--key")],
    output: Annotated[Path, typer.Option("--output")],
    retain_local_draft: Annotated[bool, typer.Option("--retain-local-draft")] = False,
    output_format: Annotated[Literal["html", "json"], typer.Option("--format")] = "html",
) -> None:
    """Retain one bounded local CPU draft from PUBLIC passages; support is not assessed."""
    _research_draft(request_id, config, output, output_format, key, retain_local_draft)


@research_app.command("inspect-draft")
def inspect_research_draft(
    request_id: str,
    config: Annotated[Path, typer.Option("--config")],
    output: Annotated[Path, typer.Option("--output")],
    output_format: Annotated[Literal["html", "json"], typer.Option("--format")] = "html",
) -> None:
    """Revalidate and export a retained draft without inference or network access."""
    _research_draft(request_id, config, output, output_format, None, False)


def _research_draft(request: str, config: Path, output: Path, format: str, key: str | None, intent: bool) -> None:
    from panestria.config_synthesis import load_synthesis_settings
    from panestria.contracts.research_synthesis import synthesis_json
    from panestria.execution.research_synthesis import OwnerSynthesis, synthesis_html

    try:
        _draft_output_preflight(output)
        settings = load_synthesis_settings(config, need_model=key is not None)
        dsn = Settings(database_url=os.environ.get("PANESTRIA_DATABASE_URL", "")).validate_profile().database_url
        service = OwnerSynthesis(dsn.get_secret_value(), settings)
        receipt = service.synthesize(request, key, retain_local_draft=intent) if key is not None else None
        if receipt is not None and receipt.status != "DRAFT_RETAINED":
            typer.echo(json.dumps(asdict(receipt)))
            raise typer.Exit(1)
        draft = service.inspect(request)
        raw = synthesis_html(draft) if format == "html" else synthesis_json(draft)
        _write_private(output, raw)
        typer.echo(
            json.dumps(
                {
                    "status": "DRAFT_EXPORTED",
                    "synthesis_id": draft.synthesis_id,
                    "claim_count": len(draft.response.claims),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "semantic_support": "NOT_ASSESSED",
                    "task_completion_authority": "NONE",
                    "replayed": receipt.replayed if receipt is not None else True,
                }
            )
        )
    except typer.Exit:
        raise
    except (Exception, KeyboardInterrupt):
        # Intent may already be committed; this never promises a safe redispatch.
        typer.echo('{"status":"UNAVAILABLE","reason":"research_draft_unavailable_inspect_state"}', err=True)
        raise typer.Exit(1) from None


@research_app.command("prepare-draft-review")
def prepare_draft_review(
    request_id: str,
    config: Annotated[Path, typer.Option("--config")],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    """Export an unreviewed template bound to exact claims and retained passages."""
    _owner_review("prepare", request_id, config, output=output)


@research_app.command("review-draft")
def review_draft_terminal(
    request_id: str,
    config: Annotated[Path, typer.Option("--config")],
) -> None:
    """Review retained claims/passages and separately confirm exact owner judgments."""
    from panestria.cli.research_review_terminal import run_research_review_terminal
    from panestria.config_synthesis import load_synthesis_settings
    from panestria.execution.research_review import OwnerResearchReview

    try:
        settings = load_synthesis_settings(config, need_model=False)
        dsn = Settings(database_url=os.environ.get("PANESTRIA_DATABASE_URL", "")).validate_profile().database_url
        run_research_review_terminal(OwnerResearchReview(dsn.get_secret_value(), settings), request_id)
    except (Exception, KeyboardInterrupt):
        typer.echo('{"status":"UNAVAILABLE","reason":"owner_review_unavailable_inspect_state"}', err=True)
        raise typer.Exit(1) from None


@research_app.command("check-draft-review")
def check_draft_review(
    request_id: str,
    config: Annotated[Path, typer.Option("--config")],
    review: Annotated[Path, typer.Option("--review")],
) -> None:
    """Validate completed owner judgments and show their exact confirmation digest."""
    _owner_review("check", request_id, config, review=review)


@research_app.command("record-draft-review")
def record_draft_review(
    request_id: str,
    config: Annotated[Path, typer.Option("--config")],
    review: Annotated[Path, typer.Option("--review")],
    sha256: Annotated[str, typer.Option("--sha256")],
    accept_owner_review: Annotated[bool, typer.Option("--accept-owner-review")] = False,
) -> None:
    """Retain exact owner judgments; this grants no automatic support or task PASS."""
    _owner_review("record", request_id, config, review=review, digest=sha256, intent=accept_owner_review)


@research_app.command("inspect-draft-review")
def inspect_draft_review(
    request_id: str,
    config: Annotated[Path, typer.Option("--config")],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    """Revalidate and privately export the latest retained owner review, without inference."""
    _owner_review("inspect", request_id, config, output=output)


def _owner_review(
    verb: Literal["prepare", "check", "record", "inspect"],
    request: str,
    config: Path,
    *,
    output: Path | None = None,
    review: Path | None = None,
    digest: str | None = None,
    intent: bool = False,
) -> None:
    from panestria.config_synthesis import load_synthesis_settings
    from panestria.contracts.research_review import review_json
    from panestria.execution.research_review import OwnerResearchReview

    try:
        if output is not None:
            _draft_output_preflight(output)
        settings = load_synthesis_settings(config, need_model=False)
        dsn = Settings(database_url=os.environ.get("PANESTRIA_DATABASE_URL", "")).validate_profile().database_url
        service = OwnerResearchReview(dsn.get_secret_value(), settings)
        if verb in {"prepare", "inspect"}:
            assert output is not None
            result = service.prepare_review(request) if verb == "prepare" else service.inspect_review(request)
            body = review_json(result)
            _write_private(output, body)
            typer.echo(json.dumps({"status": "REVIEW_EXPORTED", "sha256": hashlib.sha256(body).hexdigest()}))
        else:
            assert review is not None
            raw = read_private(review, 16384)
            if verb == "check":
                typer.echo(json.dumps({"status": "REVIEW_READY", "sha256": service.check_review(request, raw)}))
            else:
                assert digest is not None
                typer.echo(json.dumps(service.record_review(request, raw, digest, accept_owner_review=intent)))
    except (Exception, KeyboardInterrupt):
        typer.echo('{"status":"UNAVAILABLE","reason":"owner_review_unavailable_inspect_state"}', err=True)
        raise typer.Exit(1) from None
