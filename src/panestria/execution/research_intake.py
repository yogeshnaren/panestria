"""Frozen owner template and existing local-only staging/verified inspection."""

import os
from pathlib import Path
from uuid import UUID, uuid5

import psycopg
from pydantic import BaseModel, ConfigDict, JsonValue

from panestria.config_local import read_private
from panestria.contracts.build import canonical_sha256
from panestria.contracts.goal import load_contract
from panestria.contracts.research import ResearchLimits
from panestria.contracts.research_intake import ResearchIntakeSubmission, ResearchIntakeView, ResearchStagingView
from panestria.execution.research_brief import RetainedBrief
from panestria.execution.research_submission import stage_question
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork


class IntakeConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)
    schema_version: int
    root: Path
    contract_template: dict[str, JsonValue]
    limits: ResearchLimits


class ResearchIntakeService:
    def __init__(self, path: Path, actor: Actor):
        config = IntakeConfiguration.model_validate_json(read_private(path, 256 * 1024))
        if type(config.schema_version) is not int or config.schema_version != 1:
            raise KernelDenied("research_intake_configuration_invalid")
        contract = load_contract(config.contract_template)
        root = config.root
        if (contract.owner_id, contract.project_id, contract.privacy_class) != (
            actor.owner_id,
            actor.project_id,
            "PUBLIC",
        ):
            raise KernelDenied("public_research_submission_required")
        if (
            not root.is_absolute()
            or root.resolve(strict=True) != root
            or not root.is_dir()
            or root.stat().st_uid != os.getuid()
            or root.stat().st_mode & 0o077
        ):
            raise KernelDenied("private_research_directory_required")
        self.root, self.actor = root, actor
        self.view = ResearchIntakeView(
            owner_id=actor.owner_id,
            project_id=actor.project_id,
            template_sha256=canonical_sha256(config.model_dump(mode="json")),
            contract_template=contract.model_dump(mode="json"),
            limits=config.limits,
        )
        if len(self.view.model_dump_json().encode()) > 128 * 1024:
            raise KernelDenied("research_intake_template_limit")

    def stage(self, uow: UnitOfWork, dsn: str, actor: Actor, body: ResearchIntakeSubmission) -> str:
        if (actor.owner_id, actor.project_id) != (
            self.actor.owner_id,
            self.actor.project_id,
        ) or body.template_sha256 != self.view.template_sha256:
            raise KernelDenied("research_intake_template_changed")
        document = {**self.view.contract_template, "goal_id": body.goal_id}
        receipt = stage_question(
            dsn,
            actor,
            self.root,
            document,
            body.question,
            self.view.limits,
            "mission-research:" + body.goal_id,
            public_question=body.public_question,
            uow=uow,
        )
        return receipt.goal_id

    def inspect(self, dsn: str, actor: Actor, goal: str) -> ResearchStagingView:
        if (actor.owner_id, actor.project_id) != (self.actor.owner_id, self.actor.project_id) or str(
            UUID(goal)
        ) != goal:
            raise KernelDenied("not_found")
        task = str(uuid5(UUID(goal), "owner-research-task-v1"))
        request = str(uuid5(UUID(goal), "owner-research-request-v1"))
        brief = RetainedBrief(self.root, actor).inspect(dsn, request, task)
        if brief.privacy_label != "PUBLIC":
            raise KernelDenied("public_research_submission_required")
        with psycopg.connect(dsn, connect_timeout=2, options="-c statement_timeout=5000 -c lock_timeout=1000") as db:
            row = db.execute(
                "SELECT max_sources,max_source_bytes,max_total_bytes,max_redirects,deadline_seconds"
                " FROM panestria.research_request WHERE id=%s AND task_id=%s AND owner_id=%s"
                " AND project_id=%s AND request_sha256=%s",
                (request, task, actor.owner_id, actor.project_id, brief.request_sha256),
            ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        limits = ResearchLimits(
            max_sources=row[0],
            max_source_bytes=row[1],
            max_total_bytes=row[2],
            max_redirects=row[3],
            deadline_seconds=float(row[4]),
        )
        return ResearchStagingView(
            owner_id=actor.owner_id,
            project_id=actor.project_id,
            goal_id=goal,
            task_id=task,
            request_id=request,
            request_sha256=brief.request_sha256,
            question=brief.question.get_secret_value(),
            goal_status=brief.goal_status,
            task_state=brief.task_state,
            limits=limits,
        )
