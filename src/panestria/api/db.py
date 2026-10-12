"""Bounded database connections for request handlers."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, TypeVar

import psycopg

T = TypeVar("T")


class DatabaseUnavailable(Exception):
    """The database could not be reached. The message is not the URL."""


def open_database(url: str) -> psycopg.Connection[Any]:
    try:
        return psycopg.connect(
            url,
            connect_timeout=2,
            options="-c statement_timeout=2000 -c lock_timeout=2000",
        )
    except psycopg.Error:
        raise DatabaseUnavailable from None


async def run_database(function: Callable[..., T], /, *args: Any) -> T:
    """Run one synchronous database call off the request listener."""
    return await asyncio.to_thread(function, *args)
