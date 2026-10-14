"""Stable denial codes. Messages do not include caller documents."""

from __future__ import annotations


class KernelDenied(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)
