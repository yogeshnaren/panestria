"""Caller-owned database transaction. Repositories do not commit it."""

from __future__ import annotations

from typing import Any

import psycopg


class UnitOfWork:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self.connection = connection

    def execute(self, query: str, params: tuple[object, ...] = ()) -> psycopg.Cursor[tuple[Any, ...]]:
        return self.connection.execute(query, params)
