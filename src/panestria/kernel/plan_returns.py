"""Historical physical-return release, never a retry, PASS or UNKNOWN reclassification.

The trusted controller's canonical returned receipts must prove every claimed
native/tool/final operation ended. A native candidate also needs a published
published verifier bundle; native return alone says nothing about later verification.
"""

from __future__ import annotations

import json
from typing import Any

from panestria.contracts.acceptance import TrustedCommandRef
from panestria.contracts.build import canonical_sha256
from panestria.contracts.goal import contract_sha256
from panestria.contracts.invocation import InvocationBinding
from panestria.contracts.plan import PlanTaskScope
from panestria.kernel.build import BuildEvidenceStore, _contract
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.plan_lifecycle import PlanLifecycle
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.uow import UnitOfWork

# A completed runner receipt or a trusted prelaunch refusal. Unknown cleanup is
# deliberately absent. These are physical lifecycle reasons, never quality PASS.
_SAFE_CHECKS = {
    "ok",
    "process_failed",
    "deadline_exceeded",
    "memory_limit",
    "output_limit",
    "deadline",
    "unregistered_command",
    "unreviewed_executable_or_args",
    "unreviewed_path",
    "bundle_tampered",
    "plan_path_denied",
}


class ReturnedBuildRelease:
    def __init__(self, store: BuildEvidenceStore):
        self.store = store

    def _report(self, digest: str) -> dict[str, Any]:
        try:
            result = json.loads(self.store.read_blob(digest))
            if not isinstance(result, dict):
                raise ValueError
            return result
        except (ValueError, TypeError):
            raise KernelDenied("build_return_report_invalid") from None

    def release(self, uow: UnitOfWork, actor: Actor, plan_id: str, attempt_id: str) -> str:
        lifecycle = PlanLifecycle()
        plan = lifecycle._locked(uow, actor, plan_id)
        claim = uow.execute(
            "SELECT c.task_id::text,c.lease_epoch,c.released_at,t.state,a.status,c.worker_ref "
            "FROM panestria.build_worker_claim c JOIN panestria.task t ON t.id=c.task_id "
            "JOIN panestria.task_attempt a ON a.id=c.attempt_id WHERE c.plan_id=%s AND c.attempt_id=%s FOR UPDATE OF a",
            (plan_id, attempt_id),
        ).fetchone()
        if claim is None:
            raise KernelDenied("not_found")
        task, epoch, handed_off, state, attempt_status, worker_ref = claim
        prior = uow.execute(
            "SELECT reason,proof,proof_sha256 FROM panestria.build_claim_release WHERE attempt_id=%s", (attempt_id,)
        ).fetchone()
        if prior:
            proof = prior[1]
            if (
                prior[0] != "VERIFIED_RETURN"
                or canonical_sha256(proof) != str(prior[2]).strip()
                or proof.get("plan_id") != plan_id
                or proof.get("attempt_id") != attempt_id
            ):
                raise KernelDenied("build_return_release_conflict")
            return str(prior[2]).strip()
        if (
            handed_off is not None
            or state not in {"FAILED", "REJECTED", "CANCELLED", "CANCELLING", "RECONCILING"}
            or attempt_status not in {"FAILED", "CANCELLED", "CANCELLING", "RUNNING", "SUCCEEDED"}
        ):
            raise KernelDenied("fenced_build_return_required")
        # RECONCILING/RUNNING is admitted only for the final conflict/return path;
        # an intermediate candidate may still have a verifier outside native I/O.
        if state == "RECONCILING" and worker_ref != "trusted-integrator":
            raise KernelDenied("intermediate_verifier_return_unconfirmed")
        if (
            uow.execute(
                "SELECT 1 FROM panestria.side_effect WHERE task_id=%s AND state!='PREPARED' LIMIT 1", (task,)
            ).fetchone()
            or uow.execute(
                "SELECT 1 FROM panestria.task_attempt WHERE task_id=%s AND id!=%s "
                "AND status IN ('PENDING','RUNNING','CANCELLING') LIMIT 1",
                (task, attempt_id),
            ).fetchone()
        ):
            raise KernelDenied("build_return_effect_or_attempt_unconfirmed")
        rows = uow.execute(
            "SELECT id::text,state,binding,binding_sha256,receipt_sha256 FROM panestria.worker_invocation "
            "WHERE attempt_id=%s ORDER BY id FOR UPDATE",
            (attempt_id,),
        ).fetchall()
        if not rows or any(row[1] not in {"RETURNED", "PREPARED"} for row in rows):
            raise KernelDenied("build_return_invocations_unconfirmed")
        observed = []
        native_candidates = 0
        native_count = integration_count = 0
        for identity, status, body, binding_sha, digest in rows:
            try:
                binding = InvocationBinding.model_validate_json(json.dumps(body))
            except ValueError:
                raise KernelDenied("build_return_binding_invalid") from None
            if binding.sha256() != str(binding_sha).strip() or (
                str(binding.scope.owner_id),
                str(binding.scope.project_id),
                str(binding.scope.task_id),
                str(binding.scope.attempt_id),
                binding.scope.lease_epoch,
            ) != (actor.owner_id, actor.project_id, task, attempt_id, epoch):
                raise KernelDenied("build_return_scope_mismatch")
            cid, contract = _contract(uow, actor, task)
            if (
                binding.scope.contract_sha256 != contract_sha256(contract)
                or binding.scope.policy_ref != contract.autonomy_profile_ref
            ):
                raise KernelDenied("build_return_contract_mismatch")
            if status == "PREPARED":
                observed.append({"invocation_id": identity, "state": "PREPARED", "binding_sha256": binding.sha256()})
                continue
            if digest is None:
                raise KernelDenied("build_return_receipt_missing")
            digest = str(digest).strip()
            report = self._report(digest)
            if report.get("scope_sha256") != binding.scope.sha256():
                raise KernelDenied("build_return_scope_mismatch")
            if binding.kind == "native-proposal":
                native_count += 1
                observation = report.get("observation", {})
                if not isinstance(observation, dict):
                    raise KernelDenied("native_physical_return_unconfirmed")
                process = observation.get("process", {})
                if (
                    report.get("kind") != "admitted-native-build"
                    or report.get("context_sha256") != binding.request_sha256
                    or observation.get("profile") != "claude-subscription-public-bash-v1"
                    or observation.get("hostile_configuration_ignored") is not True
                    or not isinstance(process, dict)
                    or process.get("terminated") is not True
                    or process.get("status") not in {"CANDIDATE", "UNAVAILABLE", "REJECTED", "FAILED", "CANCELLED"}
                ):
                    raise KernelDenied("native_physical_return_unconfirmed")
                native_candidates += process.get("status") == "CANDIDATE"
            elif binding.kind == "native-tool":
                if (
                    report.get("kind") != "scoped-bash"
                    or report.get("request_sha256") != binding.request_sha256
                    or report.get("invocation_id") != identity
                    or type(report.get("exit_code")) is not int
                ):
                    raise KernelDenied("tool_physical_return_unconfirmed")
            elif binding.kind == "build-integration":
                integration_count += 1
                if (
                    report.get("kind") != "build-integration-return"
                    or report.get("physical_return") != "CONFIRMED"
                    or report.get("binding_sha256") != binding.sha256()
                ):
                    raise KernelDenied("integration_physical_return_unconfirmed")
                inputs = self._report(report.get("integration_report_sha256", ""))
                if (
                    inputs.get("plan_id"),
                    inputs.get("attempt_id"),
                    inputs.get("lease_epoch"),
                    inputs.get("inputs_sha256"),
                ) != (plan_id, attempt_id, epoch, binding.request_sha256):
                    raise KernelDenied("integration_return_inputs_changed")
                for check_sha in report.get("verifier_report_sha256", []):
                    self.store.read_blob(check_sha)
            observed.append(
                {
                    "invocation_id": identity,
                    "state": "RETURNED",
                    "binding_sha256": binding.sha256(),
                    "receipt_sha256": digest,
                }
            )
        if worker_ref == "claude-public-bash":
            if native_count != 1 or integration_count:
                raise KernelDenied("native_return_profile_unconfirmed")
            if native_candidates:
                # The model can return before independent verification starts.
                # Require an actual published bundle and cleaned check
                # receipts; cancellation with no bundle remains safely held.
                records = uow.execute(
                    "SELECT sha256,body FROM panestria.build_evidence WHERE task_id=%s AND attempt_id=%s",
                    (task, attempt_id),
                ).fetchall()
                if len(records) != 1:
                    raise KernelDenied("intermediate_verifier_return_unconfirmed")
                bundle = self.store.read(str(records[0][0]).strip())
                if (
                    (state == "FAILED" and bundle.passed())
                    or json.loads(bundle.canonical_bytes()) != records[0][1]
                    or (bundle.owner_id, bundle.project_id, bundle.task_id, bundle.attempt_id, bundle.lease_epoch)
                    != (actor.owner_id, actor.project_id, task, attempt_id, epoch)
                    or bundle.contract_sha256 != contract_sha256(contract)
                    or bundle.contract_id != cid
                ):
                    raise KernelDenied("failed_verifier_return_unconfirmed")
                sinks = {n.task_id for n in plan.proposal.nodes} - {
                    d for n in plan.proposal.nodes for d in n.depends_on
                }
                node = next(n for n in plan.proposal.nodes if n.task_id == task)
                if len(sinks) != 1:
                    raise KernelDenied("plan_integration_unconfirmed")
                scope = PlanTaskScope(
                    plan_id=plan_id,
                    plan_sha256=plan.proposal.sha256(),
                    inventory_sha256=plan.inventory.sha256(),
                    node=node,
                    integration_task_id=next(iter(sinks)),
                )
                checks = {check.id: check for check in contract.acceptance if check.id in node.acceptance_keys}
                if set(check.check_key for check in bundle.checks) != set(checks):
                    raise KernelDenied("failed_verifier_checks_unconfirmed")
                for check in bundle.checks:
                    data = self._report(check.report_sha256)
                    if (
                        data.get("plan_scope_sha256") != scope.sha256()
                        or check.spec_sha256
                        != canonical_sha256(checks[check.check_key].verifier.model_dump(mode="json"))
                        or (
                            isinstance(checks[check.check_key].verifier, TrustedCommandRef)
                            and data.get("reason") not in _SAFE_CHECKS
                        )
                    ):
                        raise KernelDenied("failed_verifier_cleanup_unconfirmed")
        elif worker_ref != "trusted-integrator" or integration_count != 1 or native_count:
            raise KernelDenied("build_return_profile_unconfirmed")
        proof = {
            "plan_id": plan_id,
            "plan_sha256": plan.proposal.sha256(),
            "task_id": task,
            "attempt_id": attempt_id,
            "lease_epoch": epoch,
            "reason": "VERIFIED_RETURN",
            "invocations": observed,
            "task_state_before_release": state,
            "execution_authority": "NONE",
        }
        digest = lifecycle._release(uow, attempt_id, "VERIFIED_RETURN", proof)
        if state == "CANCELLING" or (state == "RECONCILING" and worker_ref == "trusted-integrator"):
            uow.execute("UPDATE panestria.task SET state='CANCELLED',row_version=row_version+1 WHERE id=%s", (task,))
            uow.execute(
                "UPDATE panestria.task_attempt SET status='CANCELLED',finished_at=clock_timestamp() "
                "WHERE id=%s AND status IN ('PENDING','RUNNING','CANCELLING')",
                (attempt_id,),
            )
        append_event(
            uow,
            goal_id=plan.proposal.goal_id,
            task_id=task,
            actor=actor.owner_id,
            kind="build.plan.returned_capacity_released",
            payload={
                "plan_id": plan_id,
                "attempt_id": attempt_id,
                "proof_sha256": digest,
                "dispatch_authority": "NONE",
            },
        )
        return digest
