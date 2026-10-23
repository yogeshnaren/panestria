"""Closed requested model choices for the pinned subscription profiles.

These are request identifiers, not evidence of account availability, billing,
provider weights or quality. Floating aliases and hybrid/credit routes are absent.
"""

from typing import Literal

NativeModel = Literal["claude-haiku-4-5-20251001", "claude-sonnet-5", "claude-opus-5"]
NATIVE_MODELS: tuple[NativeModel, ...] = ("claude-haiku-4-5-20251001", "claude-sonnet-5", "claude-opus-5")


def validate_native_model(value: str | None) -> NativeModel | None:
    if value is None:
        return None
    for model in NATIVE_MODELS:
        if type(value) is str and value == model:
            return model
    raise ValueError("unsupported_native_model")
