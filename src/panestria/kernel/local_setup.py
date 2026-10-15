"""Explicit offline-read setup; no fabricated task, certification or provider grant."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from panestria.contracts.policy import Action, Autonomy, AutonomyAxis, PolicyContext, PrivacyAxis, TrustAxis
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.repositories.policy import current_policy, insert_revision, lock_project
from panestria.kernel.uow import UnitOfWork


class LocalSetupIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    owner_id: UUID
    project_id: UUID
    intent: Literal["OFFLINE_ASK"]

    def actor(self) -> Actor:
        return Actor(str(self.owner_id), str(self.project_id))


@dataclass(frozen=True)
class LocalSetupReceipt:
    owner_id: str
    project_id: str
    policy_ref: str
    replayed: bool


def offline_policy(actor: Actor) -> PolicyContext:
    actions: dict[Action, Autonomy] = {
        action: "observe"
        for action in ("read", "edit", "tool-install", "external-send", "spend", "merge", "delete", "policy-change")
    }
    actions["read"] = "act-and-report"
    return PolicyContext(
        owner_id=actor.owner_id,
        project_id=actor.project_id,
        version=1,
        trust=TrustAxis(version=1, profile="SYNTHETIC_DEV", allowed_actions=["read"]),
        privacy=PrivacyAxis(version=1),
        autonomy=AutonomyAxis(version=1, actions=actions),
    )


class LocalSetupService:
    def initialize(self, uow: UnitOfWork, intent: LocalSetupIntent) -> LocalSetupReceipt:
        actor = intent.actor()
        uow.execute(
            "INSERT INTO panestria.principal(id,display_name) VALUES(%s,'Local owner') ON CONFLICT(id) DO NOTHING",
            (actor.owner_id,),
        )
        uow.execute(
            "INSERT INTO panestria.project(id,owner_id) VALUES(%s,%s) ON CONFLICT(id) DO NOTHING",
            (actor.project_id, actor.owner_id),
        )
        version = lock_project(uow, actor)
        expected = offline_policy(actor)
        prior = uow.execute(
            "SELECT policy_sha256 FROM panestria.local_project_setup WHERE owner_id=%s AND project_id=%s",
            (actor.owner_id, actor.project_id),
        ).fetchone()
        if version != 0:
            if prior is None or version != 1 or str(prior[0]).strip() != expected.sha256():
                raise KernelDenied("local_setup_policy_conflict")
            if current_policy(uow, actor) != expected:
                raise KernelDenied("local_setup_policy_conflict")
        else:
            if prior is not None:
                raise KernelDenied("local_setup_policy_conflict")
            insert_revision(uow, expected)
            uow.execute(
                "INSERT INTO panestria.local_project_setup"
                " (owner_id,project_id,schema_version,intent,policy_version,policy_sha256)"
                " VALUES(%s,%s,1,'OFFLINE_ASK',1,%s)",
                (actor.owner_id, actor.project_id, expected.sha256()),
            )
        return LocalSetupReceipt(
            actor.owner_id, actor.project_id, f"project-policy:1:{expected.sha256()}", prior is not None
        )
