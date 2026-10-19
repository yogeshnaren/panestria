"""Deterministic proposal preflight. Scheduling still requires canonical current admission."""

from decimal import Decimal

from panestria.contracts.goal import GoalContract, contract_sha256, load_contract
from panestria.contracts.plan import PlanProposal, ProjectInventory, ValidatedDAG
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.verification.paths import path_permitted


class PlanValidator:
    def validate(
        self, actor: Actor, proposal: PlanProposal, contract: GoalContract, inventory: ProjectInventory
    ) -> ValidatedDAG:
        # Revalidate even frozen model_copy instances. This is a pure preflight,
        # not proof that caller-supplied inventories are current/certified.
        proposal = PlanProposal.model_validate(proposal)
        inventory = ProjectInventory.model_validate(inventory)
        contract = load_contract(contract.model_dump(mode="json"))
        identity = (actor.owner_id, actor.project_id)
        if (
            identity != (proposal.owner_id, proposal.project_id)
            or identity != (contract.owner_id, contract.project_id)
            or identity != (inventory.owner_id, inventory.project_id)
            or proposal.goal_id != contract.goal_id
        ):
            raise KernelDenied("plan_scope_mismatch")
        if (
            proposal.contract_sha256 != contract_sha256(contract)
            or proposal.inventory_sha256 != inventory.sha256()
            or proposal.privacy_class != contract.privacy_class
        ):
            raise KernelDenied("plan_input_binding_changed")
        if len(proposal.nodes) > inventory.maximum_nodes:
            raise KernelDenied("plan_node_limit")
        nodes = {n.task_id: n for n in proposal.nodes}
        if len(nodes) != len(proposal.nodes):
            raise KernelDenied("plan_duplicate_task")
        workers = {w.worker_ref: w for w in inventory.workers}
        check_keys = {c.id for c in contract.acceptance}
        required = {c.id for c in contract.acceptance if c.required}
        assigned: set[str] = set()
        upper_cash = upper_wall = 0
        for node in nodes.values():
            if node.task_id in node.depends_on or set(node.depends_on) - nodes.keys():
                raise KernelDenied("plan_dependency_invalid")
            worker = workers.get(node.worker_ref)
            if (
                worker is None
                or set(node.capabilities) - set(worker.capabilities)
                or set(node.capabilities) - set(contract.constraints.permitted_capabilities)
            ):
                raise KernelDenied("plan_capability_unavailable")
            if any(
                not path_permitted(p, contract.constraints.allowed_paths, contract.constraints.forbidden_paths)
                for p in node.paths
            ):
                raise KernelDenied("plan_path_out_of_scope")
            if set(node.acceptance_keys) - check_keys:
                raise KernelDenied("plan_check_unrecognized")
            assigned.update(node.acceptance_keys)
            if node.attempts > contract.budget.max_attempts_per_task:
                raise KernelDenied("plan_attempt_limit")
            upper_cash += node.attempts * node.api_microusd_per_attempt
            upper_wall += node.attempts * node.wall_seconds_per_attempt
        if not required or required - assigned:
            raise KernelDenied("plan_required_checks_missing")
        # Sum retries and serial wall envelopes, rather than assuming concurrency
        # or subscription capacity produces a free/shorter future effect.
        if (
            upper_cash > int(Decimal(contract.budget.max_api_usd) * 1_000_000)
            or upper_wall > contract.budget.max_wall_seconds
        ):
            raise KernelDenied("plan_budget_exceeded")
        remaining = set(nodes)
        completed: set[str] = set()
        layers = []
        while remaining:
            ready = tuple(sorted(key for key in remaining if set(nodes[key].depends_on) <= completed))
            if not ready:
                raise KernelDenied("plan_cycle")
            layers.append(ready)
            if len(layers) > inventory.maximum_depth:
                raise KernelDenied("plan_depth_limit")
            completed.update(ready)
            remaining.difference_update(ready)
        return ValidatedDAG(
            proposal_sha256=proposal.sha256(),
            contract_sha256=proposal.contract_sha256,
            inventory_sha256=proposal.inventory_sha256,
            layers=tuple(layers),
            maximum_parallel=inventory.maximum_parallel,
            upper_wall_seconds=upper_wall,
            upper_api_microusd=upper_cash,
        )
