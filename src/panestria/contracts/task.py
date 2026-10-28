"""Closed task states and the edges a transition may take."""

from __future__ import annotations

from typing import Literal

TaskState = Literal[
    "CREATED",
    "VALIDATING",
    "READY",
    "LEASED",
    "RUNNING",
    "WAITING_APPROVAL",
    "VERIFYING",
    "RETRY_WAIT",
    "RECONCILING",
    "CANCELLING",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    "REJECTED",
]

_ACTIVE: frozenset[str] = frozenset(
    {
        "CREATED",
        "VALIDATING",
        "READY",
        "LEASED",
        "RUNNING",
        "WAITING_APPROVAL",
        "VERIFYING",
        "RETRY_WAIT",
        "RECONCILING",
    }
)

ALLOWED_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("CREATED", "VALIDATING"),
        ("VALIDATING", "READY"),
        ("VALIDATING", "WAITING_APPROVAL"),
        ("VALIDATING", "REJECTED"),
        ("READY", "LEASED"),
        ("LEASED", "RUNNING"),
        ("RUNNING", "VERIFYING"),
        ("RUNNING", "RECONCILING"),
        ("RUNNING", "RETRY_WAIT"),
        ("VERIFYING", "WAITING_APPROVAL"),
        ("VERIFYING", "COMPLETED"),
        ("VERIFYING", "RECONCILING"),
        ("RECONCILING", "VERIFYING"),
        ("VERIFYING", "RETRY_WAIT"),
        ("WAITING_APPROVAL", "READY"),
        ("WAITING_APPROVAL", "VERIFYING"),
        ("RETRY_WAIT", "READY"),
        ("CANCELLING", "CANCELLED"),
        *((state, "CANCELLING") for state in _ACTIVE),
        *((state, "FAILED") for state in _ACTIVE),
    }
)
