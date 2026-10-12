"""Immutable goal contract and canonical SHA-256."""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from panestria.contracts.acceptance import (
    LEGACY_VERIFIERS,
    R2_VERIFIERS,
    AcceptanceCheck,
    ContractRejected,
)

_MONEY = re.compile(r"^(0|[1-9][0-9]*)(\.[0-9]{1,6})?$")
_SHELL = re.compile(r"[\s;|&$`<>]")
_UUID = r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"


def _money(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, str) or _MONEY.fullmatch(value) is None:
        raise ValueError("invalid_money")
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("invalid_money") from exc
    if not amount.is_finite():
        raise ValueError("invalid_money")
    text = format(amount, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


class Constraints(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    allowed_paths: list[str] = Field(min_length=1)
    forbidden_paths: list[str] = Field(min_length=1)
    permitted_capabilities: list[str] = Field(min_length=1)
    cloud_egress: Literal["deny", "allow"]

    @field_validator("allowed_paths", "forbidden_paths", "permitted_capabilities")
    @classmethod
    def _items(cls, values: list[str]) -> list[str]:
        if any(item == "" for item in values):
            raise ValueError("invalid_contract")
        return values


class Budget(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    max_attempts_per_task: int = Field(ge=1, le=5)
    max_wall_seconds: int = Field(ge=1, le=3600)
    max_api_usd: Annotated[str, Field(min_length=1)]

    @field_validator("max_api_usd", mode="before")
    @classmethod
    def _usd(cls, value: object) -> str:
        return _money(value)


class GoalContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1]
    goal_id: str = Field(pattern=_UUID)
    contract_version: int = Field(ge=1)
    owner_id: str = Field(pattern=_UUID)
    project_id: str = Field(pattern=_UUID)
    intent: str = Field(min_length=1, max_length=4096)
    privacy_class: Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]
    trust_profile_id: Literal["SYNTHETIC_DEV", "PERSONAL_SANDBOX", "TRUSTED_PROJECT", "HARDENED_WORKSPACE"]
    autonomy_profile_ref: str = Field(min_length=1)
    constraints: Constraints
    budget: Budget
    acceptance: list[AcceptanceCheck] = Field(min_length=1, max_length=100)
    non_goals: list[str]

    @model_validator(mode="after")
    def _admit(self) -> Self:
        if self.privacy_class == "RESTRICTED" and self.constraints.cloud_egress != "deny":
            raise ValueError("egress_denied")
        seen: set[str] = set()
        for check in self.acceptance:
            if check.id in seen:
                raise ValueError("duplicate_check_id")
            seen.add(check.id)
            if check.verifier.type in R2_VERIFIERS:
                raise ValueError("runner_not_admitted")
            command_ref = getattr(check.verifier, "command_ref", None)
            if isinstance(command_ref, str) and _SHELL.search(command_ref):
                raise ValueError("invalid_command_ref")
        return self


def contract_sha256(contract: GoalContract) -> str:
    """SHA-256 of canonical UTF-8 JSON: sorted keys, compact separators, stable arrays."""
    payload = json.loads(contract.model_dump_json())
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_contract(data: object) -> GoalContract:
    """Validate a contract. Failures omit the submitted document."""
    if isinstance(data, dict):
        for check in data.get("acceptance", []):
            if isinstance(check, dict):
                verifier = check.get("verifier")
                if isinstance(verifier, dict) and verifier.get("type") in LEGACY_VERIFIERS:
                    raise ContractRejected("legacy_verifier")
                if isinstance(verifier, dict) and ("run" in verifier or "command" in verifier):
                    raise ContractRejected("legacy_verifier")
    try:
        return GoalContract.model_validate(data)
    except ContractRejected:
        raise
    except ValidationError as exc:
        raise ContractRejected(_code(exc)) from None
    except ValueError as exc:
        raise ContractRejected(str(exc) if str(exc) in _CODES else "invalid_contract") from None


def revise(current: GoalContract, edited: GoalContract) -> GoalContract:
    """Return a new version when the canonical body changes. Identical bodies stay put."""
    if (edited.goal_id, edited.owner_id, edited.project_id) != (
        current.goal_id,
        current.owner_id,
        current.project_id,
    ):
        raise ContractRejected("identity_changed")
    if edited.contract_version != current.contract_version:
        raise ContractRejected("version_conflict")
    if contract_sha256(edited) == contract_sha256(current):
        return current
    return edited.model_copy(update={"contract_version": current.contract_version + 1})


_CODES = frozenset(
    {
        "duplicate_check_id",
        "egress_denied",
        "invalid_command_ref",
        "invalid_contract",
        "invalid_money",
        "legacy_verifier",
        "runner_not_admitted",
    }
)


def _code(exc: ValidationError) -> str:
    for err in exc.errors():
        message = str(err.get("msg", ""))
        for code in _CODES:
            if code in message:
                return code
        if err.get("loc", ())[-1:] == ("max_api_usd",):
            return "invalid_money"
        if err.get("type") in {"union_tag_invalid", "literal_error"} and "type" in err.get("loc", ()):
            return "legacy_verifier"
    return "invalid_contract"
