"""Private-file Build DAG preflight. No database, inference, dispatch or grant."""

import json
from pathlib import Path
from typing import Annotated

import typer

from panestria.config_local import read_private
from panestria.contracts.goal import load_contract
from panestria.contracts.plan import PlanProposal, ProjectInventory
from panestria.kernel.goals import Actor
from panestria.kernel.plans import PlanValidator

plan_app = typer.Typer(no_args_is_help=True)


@plan_app.command("validate")
def validate_plan(
    owner_id: str,
    project_id: str,
    proposal: Annotated[Path, typer.Option("--proposal")],
    contract: Annotated[Path, typer.Option("--contract")],
    inventory: Annotated[Path, typer.Option("--inventory")],
) -> None:
    """Check bounded task dependencies/scope/capabilities/budget; never admits a worker."""
    try:
        result = PlanValidator().validate(
            Actor(owner_id, project_id),
            PlanProposal.model_validate_json(read_private(proposal, 128 * 1024)),
            load_contract(json.loads(read_private(contract, 256 * 1024))),
            ProjectInventory.model_validate_json(read_private(inventory, 16384)),
        )
        typer.echo(result.model_dump_json())
    except Exception:
        typer.echo('{"status":"UNAVAILABLE","reason":"plan_proposal_rejected","authority":"NONE"}', err=True)
        raise typer.Exit(1) from None
