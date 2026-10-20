"""Derive verifier scope from accepted plans; individual nodes cannot merge a goal."""

from panestria.contracts.goal import GoalContract
from panestria.contracts.plan import PlanTaskScope
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.plan_store import PlanStore
from panestria.kernel.uow import UnitOfWork


def task_plan_scope(uow: UnitOfWork, actor: Actor, task_id: str) -> PlanTaskScope | None:
    row = uow.execute("SELECT plan_id::text FROM panestria.build_plan_task WHERE task_id=%s", (task_id,)).fetchone()
    if row is None:
        return None  # Legacy one-worker behavior and evidence bytes are unchanged.
    plan = PlanStore().get(uow, actor, row[0])
    if plan.state != "ACCEPTED":
        raise KernelDenied("plan_not_accepted")
    nodes = {n.task_id: n for n in plan.proposal.nodes}
    dependents = {dependency for n in nodes.values() for dependency in n.depends_on}
    terminal = set(nodes) - dependents
    if len(terminal) != 1:
        raise KernelDenied("plan_single_integration_required")
    integration = terminal.pop()
    # A unique sink in a bounded validated DAG must cover all component nodes;
    # explicitly verify ancestry rather than relying on that implication.
    ancestors: set[str] = set()
    pending = [integration]
    while pending:
        key = pending.pop()
        if key not in ancestors:
            ancestors.add(key)
            pending.extend(nodes[key].depends_on)
    if ancestors != set(nodes):
        raise KernelDenied("plan_integration_incomplete")
    contract_row = uow.execute(
        "SELECT c.body FROM panestria.goal_contract c JOIN panestria.build_plan p ON p.contract_id=c.id WHERE p.id=%s",
        (plan.proposal.plan_id,),
    ).fetchone()
    assert contract_row is not None
    from panestria.contracts.goal import load_contract

    contract = load_contract(contract_row[0])
    if set(nodes[integration].acceptance_keys) != {c.id for c in contract.acceptance}:
        raise KernelDenied("plan_integration_requires_full_checks")
    node = nodes[task_id]
    require_node_checks(contract, node.acceptance_keys)
    return PlanTaskScope(
        plan_id=plan.proposal.plan_id,
        plan_sha256=plan.proposal.sha256(),
        inventory_sha256=plan.inventory.sha256(),
        node=node,
        integration_task_id=integration,
    )


def require_node_checks(contract: GoalContract, keys: tuple[str, ...]) -> None:
    if not any(c.required and c.id in keys for c in contract.acceptance):
        raise KernelDenied("plan_node_required_check_missing")


def require_final_task(uow: UnitOfWork, actor: Actor, task_id: str) -> None:
    scope = task_plan_scope(uow, actor, task_id)
    if scope is not None and not scope.integration:
        raise KernelDenied("plan_node_cannot_merge_goal")
