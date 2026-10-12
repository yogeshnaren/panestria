"""Bounded database connections for request handlers."""

from __future__ import annotations

from typing import Any

import psycopg


class DatabaseUnavailable(Exception):
    """The database could not be reached. The message is not the URL."""


def open_database(url: str) -> psycopg.Connection[Any]:
    try:
        return psycopg.connect(url, connect_timeout=2, options="-c statement_timeout=2000")
    except psycopg.Error:
        raise DatabaseUnavailable from None
