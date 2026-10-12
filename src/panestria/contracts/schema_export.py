"""JSON Schema rendered from the executable contract models."""

from __future__ import annotations

import json

from pydantic import BaseModel

from panestria.contracts.acceptance import AcceptanceCheck
from panestria.contracts.approval import ActionPreview
from panestria.contracts.goal import GoalContract

SCHEMA_FILES: dict[str, type[BaseModel]] = {
    "acceptance-check.schema.json": AcceptanceCheck,
    "action-preview.schema.json": ActionPreview,
    "goal-contract.schema.json": GoalContract,
}


def rendered_schemas() -> dict[str, str]:
    """Canonical JSON Schema text for each executable contract model."""
    rendered: dict[str, str] = {}
    for name, model in SCHEMA_FILES.items():
        body = json.dumps(model.model_json_schema(), indent=2, sort_keys=True)
        rendered[name] = body + "\n"
    return rendered
