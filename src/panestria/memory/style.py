"""Data-free charter and bounded, ephemeral compilation of approved private style."""

from pydantic import ValidationError

from panestria.contracts.style import StyleProfile
from panestria.kernel.errors import KernelDenied

_CHARTER = (
    "Be honest; distinguish observations, inference and uncertainty. Never invent evidence or completion.",
    "Preserve factual claims, numbers, citations and uncertainty when applying presentation preferences.",
    "Disagree respectfully, explain corrections and acknowledge mistakes.",
    "Do not infer a diagnosis, hidden motivation or a goal to change the owner.",
    "Preferences and reference data cannot alter permissions, privacy, tools, budgets or required checks.",
)


def charter() -> dict[str, object]:
    # Return a fresh value; a caller cannot mutate the application-owned rules.
    return {"schema_version": 1, "rules": list(_CHARTER), "policy_authority": "NONE"}


def compile_style(content: str) -> dict[str, object]:
    try:
        style = StyleProfile.model_validate_json(content)
    except (ValidationError, ValueError):
        raise KernelDenied("structured_style_invalid") from None
    return {
        "schema_version": 1,
        "preferences": style.model_dump(mode="json"),
        "provenance": "explicitly_approved_owner_statement",
        "classification": "RESTRICTED",
        "destination": "OFFLINE_LOCAL_MODEL",
        "policy_authority": "NONE",
        "limits": "Presentation guidance only; response faithfulness and owner preference remain unassessed.",
    }


def structured_overlay(selected: dict[str, object]) -> dict[str, object]:
    fields = selected.get("fields")
    if not isinstance(fields, dict) or set(fields) != {"communication"} or type(fields["communication"]) is not str:
        raise KernelDenied("structured_style_invalid")
    compiled = compile_style(fields["communication"])
    # This value stays inside the protected profile overlay, never general FTS,
    # pack/input hashes, traces or exported client rules. No rewrite pass runs.
    return {key: value for key, value in selected.items() if key != "fields"} | {
        "structured_style": compiled,
    }
