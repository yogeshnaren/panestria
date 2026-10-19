"""Local owner review for a dedicated PUBLIC-web research project; no dispatch."""

from dataclasses import asdict
from typing import Any
from uuid import UUID, uuid5

import psycopg

from panestria.config_research import ResearchSettings, validate_research_settings
from panestria.contracts.goal import contract_sha256, load_contract
from panestria.contracts.policy import AutonomyAxis, PolicyContext, PrivacyAxis, TrustAxis
from panestria.execution.research_runtime import research_runtime_versions
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor, GoalService
from panestria.kernel.local_setup import LocalSetupIntent, LocalSetupService, offline_policy
from panestria.kernel.policy import PolicyService
from panestria.kernel.repositories.policy import current_policy, lock_project
from panestria.kernel.uow import UnitOfWork
from panestria.policy.profiles import CertificateRejected
from panestria.policy.research_fetch import PublicFetchCertificateStore
from panestria.policy.search import PublicSearchCertificateStore


class OwnerResearchPolicy:
    def __init__(self, dsn: str, settings: ResearchSettings):
        self.dsn, self.settings = dsn, validate_research_settings(settings)
        self.actor = Actor(str(settings.owner_id), str(settings.project_id))
        versions = research_runtime_versions(self.settings.search)
        self.search = PublicSearchCertificateStore(settings.certificates, versions)
        self.fetch = PublicFetchCertificateStore(settings.certificates, versions)
        self.goal_id = str(UUID(bytes=uuid5(settings.project_id, "public-research-policy-setup").bytes, version=4))
        self.task_id = str(UUID(bytes=uuid5(UUID(self.goal_id), "policy-review").bytes, version=4))

    def connect(self) -> psycopg.Connection[Any]:
        return psycopg.connect(self.dsn, connect_timeout=2, options="-c statement_timeout=5000 -c lock_timeout=1000")

    def _validate(self, trust: TrustAxis) -> None:
        validate_research_settings(self.settings)
        if research_runtime_versions(self.settings.search) != self.search.runtime_versions:
            raise KernelDenied("research_policy_runtime_changed")
        try:
            self.search.validate(trust)
            self.fetch.validate(trust)
        except CertificateRejected as error:
            raise KernelDenied(str(error)) from None

    def _proposed(self, old: PolicyContext) -> PolicyContext:
        actions = dict(offline_policy(self.actor).autonomy.actions)
        actions["external-send"] = "act-and-report"
        axes: dict[str, TrustAxis | PrivacyAxis | AutonomyAxis] = {
            "trust": TrustAxis(
                version=old.trust.version,
                profile="PERSONAL_SANDBOX",
                allowed_actions=["read", "external-send"],
                runtime_certificate_sha256=self.settings.certificate_sha256,
            ),
            "privacy": PrivacyAxis(version=old.privacy.version, cloud_destinations=["public-web"]),
            "autonomy": AutonomyAxis(version=old.autonomy.version, actions=actions),
        }
        return old.model_copy(
            update={
                "version": old.version + 1,
                **{
                    name: axis.model_copy(update={"version": axis.version + int(axis != getattr(old, name))})
                    for name, axis in axes.items()
                },
            }
        )

    def _document(self) -> dict[str, Any]:
        # Keep the marker fixed across certificate/policy renewals. Its read-only
        # offline contract never becomes an executable research grant.
        initial = offline_policy(self.actor)
        return {
            "schema_version": 1,
            "goal_id": self.goal_id,
            "owner_id": self.actor.owner_id,
            "project_id": self.actor.project_id,
            "contract_version": 1,
            "intent": "Administrative PUBLIC research policy review; no collection or worker dispatch",
            "privacy_class": "PUBLIC",
            "trust_profile_id": initial.trust.profile,
            "autonomy_profile_ref": f"project-policy:1:{initial.sha256()}",
            "constraints": {
                "allowed_paths": ["review"],
                "forbidden_paths": [".git/**"],
                "permitted_capabilities": ["read"],
                "cloud_egress": "deny",
            },
            "budget": {"max_attempts_per_task": 1, "max_wall_seconds": 30, "max_api_usd": "0"},
            "acceptance": [
                {
                    "id": "owner-review",
                    "description": "Owner reviews and confirms the exact PUBLIC-web policy digest",
                    "required": True,
                    "evidence": {"required": True, "kind": "owner-policy-review"},
                    "verifier": {
                        "type": "human-review",
                        "reviewer_ref": self.actor.owner_id,
                        "evidence_requirements": ["Exact canonical policy-review decision"],
                    },
                }
            ],
            "non_goals": ["Collection, inference, editing and goal acceptance"],
        }

    def _marker(self, uow: UnitOfWork) -> None:
        row = uow.execute(
            "SELECT g.status,c.body,c.sha256 FROM panestria.goal g "
            "JOIN panestria.goal_contract c ON c.goal_id=g.id "
            "WHERE g.id=%s AND g.owner_id=%s AND g.project_id=%s FOR NO KEY UPDATE OF g",
            (self.goal_id, self.actor.owner_id, self.actor.project_id),
        ).fetchone()
        expected = contract_sha256(load_contract(self._document()))
        if row is None or row[0] != "CREATED" or str(row[2]).strip() != expected:
            raise KernelDenied("dedicated_research_project_required")
        if contract_sha256(load_contract(row[1])) != expected:
            raise KernelDenied("research_policy_marker_invalid")
        task = uow.execute(
            "SELECT t.state,t.lease_epoch,t.row_version FROM panestria.task t "
            "JOIN panestria.goal_contract c ON c.id=t.contract_id "
            "WHERE t.id=%s AND t.goal_id=%s AND c.goal_id=t.goal_id AND c.sha256=%s FOR UPDATE OF t",
            (self.task_id, self.goal_id, expected),
        ).fetchone()
        if task != ("CREATED", 0, 0):
            raise KernelDenied("research_policy_marker_invalid")
        if uow.execute("SELECT 1 FROM panestria.task_attempt WHERE task_id=%s", (self.task_id,)).fetchone():
            raise KernelDenied("research_policy_marker_invalid")

    def prepare(self, *, public_web_policy: bool) -> dict[str, Any]:
        if public_web_policy is not True:
            raise KernelDenied("explicit_public_web_policy_required")
        selected = self._proposed(offline_policy(self.actor))
        self._validate(selected.trust)  # Before creating any database scope.
        with self.connect() as c:
            uow = UnitOfWork(c)
            c.execute(
                "INSERT INTO panestria.principal(id,display_name) VALUES(%s,'Local owner') ON CONFLICT(id) DO NOTHING",
                (self.actor.owner_id,),
            )
            created = c.execute(
                # Concurrent inserts can collide with either the primary key or
                # the (id, owner_id) key. Scope is still checked by lock_project.
                "INSERT INTO panestria.project(id,owner_id) VALUES(%s,%s) ON CONFLICT DO NOTHING RETURNING id",
                (self.actor.project_id, self.actor.owner_id),
            ).fetchone()
            if created is not None:
                LocalSetupService().initialize(
                    uow,
                    LocalSetupIntent(
                        owner_id=self.settings.owner_id, project_id=self.settings.project_id, intent="OFFLINE_ASK"
                    ),
                )
                GoalService().submit(uow, self.actor, self._document(), "public-research-policy-setup")
                contract = c.execute(
                    "SELECT id FROM panestria.goal_contract WHERE goal_id=%s", (self.goal_id,)
                ).fetchone()
                assert contract is not None
                c.execute(
                    "INSERT INTO panestria.task(id,goal_id,contract_id,name,state) VALUES(%s,%s,%s,%s,'CREATED')",
                    (self.task_id, self.goal_id, contract[0], "Administrative PUBLIC research policy review"),
                )
            lock_project(uow, self.actor)
            self._marker(uow)  # Existing offline Ask projects have no marker and cannot be widened.
            old = current_policy(uow, self.actor)
            proposed = self._proposed(old)
            # A dedicated scope must still have the initial read-only or narrow
            # research axes; never carry unrelated grants into this workflow.
            prior = proposed.model_copy(
                update={
                    "trust": proposed.trust.model_copy(
                        update={"runtime_certificate_sha256": old.trust.runtime_certificate_sha256}
                    )
                }
            )
            if old != offline_policy(self.actor) and any(
                getattr(old, axis).model_dump(exclude={"version"})
                != getattr(prior, axis).model_dump(exclude={"version"})
                for axis in ("trust", "privacy", "autonomy")
            ):
                raise KernelDenied("research_policy_scope_changed")
            if all(getattr(old, axis) == getattr(proposed, axis) for axis in ("trust", "privacy", "autonomy")):
                return {"state": "CURRENT", **self._receipt(old), "replayed": True}
            review = PolicyService(self.search).propose(uow, self.actor, self.task_id, proposed)
            self._validate(proposed.trust)
            return {
                **asdict(review),
                "proposed_policy": proposed.model_dump(),
                "proposed_sha256": proposed.sha256(),
                "scope": "PUBLIC web collection only; no inference, private-cloud, edits, spend or acceptance",
            }

    def confirm(self, review_id: str, digest: str, *, public_web_policy: bool) -> dict[str, Any]:
        if public_web_policy is not True:
            raise KernelDenied("explicit_public_web_policy_required")
        self._validate(self._proposed(offline_policy(self.actor)).trust)
        with self.connect() as c:
            uow = UnitOfWork(c)
            old, state = self._review(uow, review_id, digest)
            if state == "APPLIED":
                return {"state": state, **self._receipt(old), "replayed": True}
            PolicyService(self.search).decide(uow, self.actor, review_id, digest, "approve")
        # Acknowledged approval and application are separate canonical phases.
        # A crash may leave APPROVED without a grant; retry revalidates scope,
        # digest, policy and both certificates before applying. No writes follow
        # either service's final global event allocation.
        with self.connect() as c:
            uow = UnitOfWork(c)
            old, state = self._review(uow, review_id, digest)
            if state == "APPLIED":
                return {"state": state, **self._receipt(old), "replayed": True}
            policy = PolicyService(self.search).apply(uow, self.actor, review_id, digest)
            self._validate(policy.trust)
            return {"state": "APPLIED", **self._receipt(policy), "replayed": False}

    def _review(self, uow: UnitOfWork, review_id: str, digest: str) -> tuple[PolicyContext, str]:
        lock_project(uow, self.actor)
        self._marker(uow)
        row = uow.execute(
            "SELECT state,effect_digest,proposed_body,expires_at>clock_timestamp() "
            "FROM panestria.policy_review WHERE id=%s AND owner_id=%s AND project_id=%s AND task_id=%s FOR UPDATE",
            (review_id, self.actor.owner_id, self.actor.project_id, self.task_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        if str(row[1]).strip() != digest or row[3] is not True:
            raise KernelDenied("review_mismatch")
        old = current_policy(uow, self.actor)
        proposed = PolicyContext.model_validate(row[2])
        if proposed.trust.runtime_certificate_sha256 != self.settings.certificate_sha256:
            raise KernelDenied("research_policy_certificate_changed")
        self._validate(proposed.trust)
        if not (row[0] == "APPLIED" and proposed == old) and proposed != self._proposed(old):
            raise KernelDenied("research_policy_review_changed")
        return old, str(row[0])

    @staticmethod
    def _receipt(policy: PolicyContext) -> dict[str, Any]:
        return {"policy_ref": f"project-policy:{policy.version}:{policy.sha256()}", "policy": policy.model_dump()}
