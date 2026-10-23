"""Optional trusted-controller intersection, never constructed from worker data."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import psycopg


@dataclass(frozen=True)
class WorkerAuthority:
    binding_sha256: str
    authorize: Callable[[psycopg.Connection[Any]], None]
    refresh: Callable[[], None]
