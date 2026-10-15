"""Policy repository shares the caller's transaction and actor scope."""

from __future__ import annotations

from panestria.contracts.policy import PolicyContext
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork


def lock_project(uow: UnitOfWork, actor: Actor) -> int:
    row = uow.execute(
        "SELECT policy_version FROM panestria.project WHERE id=%s AND owner_id=%s FOR UPDATE",
        (actor.project_id, actor.owner_id),
    ).fetchone()
    if row is None:
        raise KernelDenied("not_found")
    return int(row[0])


def current_policy(uow: UnitOfWork, actor: Actor) -> PolicyContext:
    row = uow.execute(
        "SELECT r.body,r.sha256 FROM panestria.project p"
        " JOIN panestria.project_policy_revision r ON r.project_id=p.id AND r.version=p.policy_version"
        " WHERE p.id=%s AND p.owner_id=%s",
        (actor.project_id, actor.owner_id),
    ).fetchone()
    if row is None:
        raise KernelDenied("policy_unconfigured")
    policy = PolicyContext.model_validate(row[0])
    if policy.sha256() != str(row[1]).strip():
        raise KernelDenied("policy_corrupt")
    return policy


def active_policy_ref(uow: UnitOfWork, owner_id: str, project_id: str) -> str | None:
    row = uow.execute(
        "SELECT p.policy_version,r.sha256 FROM panestria.project p"
        " JOIN panestria.project_policy_revision r ON r.project_id=p.id AND r.version=p.policy_version"
        " WHERE p.id=%s AND p.owner_id=%s",
        (project_id, owner_id),
    ).fetchone()
    return None if row is None else f"project-policy:{row[0]}:{str(row[1]).strip()}"


def insert_revision(uow: UnitOfWork, policy: PolicyContext) -> None:
    uow.execute(
        "INSERT INTO panestria.project_policy_revision"
        " (project_id,owner_id,version,trust_version,privacy_version,autonomy_version,body,sha256)"
        " VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s)",
        (
            policy.project_id,
            policy.owner_id,
            policy.version,
            policy.trust.version,
            policy.privacy.version,
            policy.autonomy.version,
            policy.model_dump_json(),
            policy.sha256(),
        ),
    )
    uow.execute(
        "UPDATE panestria.project SET policy_version=%s,trust_profile_id=%s,trust_profile_version=%s"
        " WHERE id=%s AND owner_id=%s",
        (policy.version, policy.trust.profile, policy.trust.version, policy.project_id, policy.owner_id),
    )


def require_current_policy(uow: UnitOfWork, actor: Actor, supplied_ref: str) -> None:
    # Lock project before approvals/effects. Policy changes cannot race dispatch.
    row = uow.execute(
        "SELECT p.policy_version,r.sha256 FROM panestria.project p"
        " LEFT JOIN panestria.project_policy_revision r ON r.project_id=p.id AND r.version=p.policy_version"
        " WHERE p.id=%s AND p.owner_id=%s FOR SHARE OF p",
        (actor.project_id, actor.owner_id),
    ).fetchone()
    if row is None:
        raise KernelDenied("not_found")
    if row[0] != 0 and supplied_ref != f"project-policy:{row[0]}:{str(row[1]).strip()}":
        raise KernelDenied("policy_mismatch")
